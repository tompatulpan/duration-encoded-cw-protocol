#!/usr/bin/env python3
"""
CW Receiver with FEC - Receive CW with Forward Error Correction
"""

import socket
import sys
import time
import threading
import queue
import argparse
from cw_protocol_fec import CWProtocolFEC, FECDecoder, UDP_PORT
from cw_protocol import CWTimingStats

# Import audio from standard receiver
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: pyaudio not available, audio sidetone disabled")
    print("Install with: pip3 install pyaudio")


# Import JitterBuffer and SidetoneGenerator from standard receiver
from cw_receiver import JitterBuffer, SidetoneGenerator


class CWReceiverFEC:
    """CW Receiver with FEC support"""
    
    def __init__(self, port=UDP_PORT, enable_audio=True, jitter_buffer_ms=0, debug=False):
        self.port = port
        self.jitter_buffer_ms = jitter_buffer_ms
        self.debug = debug
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Increase UDP receive buffer
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)
        except:
            pass
        
        self.socket.bind(('0.0.0.0', port))
        
        self.protocol = CWProtocolFEC()
        self.stats = CWTimingStats()
        
        # FEC decoder
        if self.protocol.fec_enabled:
            self.fec_decoder = FECDecoder()
        else:
            self.fec_decoder = None
        
        # Track processed packet sequences to avoid duplicates
        self.processed_sequences = set()
        
        # Audio sidetone
        self.sidetone = None
        if enable_audio and AUDIO_AVAILABLE:
            self.sidetone = SidetoneGenerator(frequency=700)
        
        # Jitter buffer
        self.jitter_buffer = None
        if jitter_buffer_ms > 0:
            self.jitter_buffer = JitterBuffer(jitter_buffer_ms)
            self.jitter_buffer.debug = debug
        
        self.last_sequence = -1
        self.packet_count = 0
        self.fec_packet_count = 0
        self.lost_packets = 0
        self.recovered_packets = 0
        self.last_packet_time = 0
        
        print(f"CW Receiver with FEC listening on port {port}")
        if self.protocol.fec_enabled:
            print(f"FEC enabled: {self.protocol.FEC_BLOCK_SIZE} data + {self.protocol.FEC_REDUNDANCY} redundancy")
            print(f"Can recover from up to {self.protocol.FEC_REDUNDANCY} lost packets per block")
        else:
            print("FEC disabled (reedsolo not installed)")
        
        if self.sidetone:
            print("Audio sidetone enabled (700 Hz)")
        else:
            print("Audio sidetone disabled (visual only)")
        
        if self.jitter_buffer:
            print(f"Jitter buffer enabled ({jitter_buffer_ms}ms)")
        else:
            print("Jitter buffer disabled (LAN mode)")
        print("-" * 60)
    
    def _process_event(self, key_down, duration_ms, seq=0):
        """Process a CW event"""
        self.stats.add_event(key_down, duration_ms)
        
        if self.debug:
            state_name = "DOWN" if key_down else "UP  "
            print(f"\n[PLAY] {state_name} for {duration_ms}ms")
        
        # Update audio sidetone
        if self.sidetone:
            self.sidetone.set_key(key_down)
        
        # Visual feedback
        state_str = "█" * 40 if key_down else " " * 40
        status = "DOWN" if key_down else "UP  "
        
        fec_info = ""
        if self.protocol.fec_enabled:
            fec_info = f" FEC:{self.fec_packet_count:3d} Rcv:{self.recovered_packets:2d}"
        
        jitter_info = ""
        if self.jitter_buffer:
            jitter_stats = self.jitter_buffer.get_stats()
            jitter_info = f" JBuf:{jitter_stats['queued_events']:2d}"
        
        print(f"\r[{state_str}] {status} {duration_ms:4d}ms | "
              f"Seq:{seq:3d} Pkts:{self.packet_count:4d} "
              f"Lost:{self.lost_packets:2d}{fec_info}{jitter_info}",
              end='', flush=True)
    
    def run(self):
        """Main receive loop"""
        # Start jitter buffer playout thread if enabled
        if self.jitter_buffer:
            self.jitter_buffer.start(lambda kd, dur: self._process_event(kd, dur))
        
        try:
            while True:
                # Receive packet
                data, addr = self.socket.recvfrom(1024)
                receive_time = time.time()
                
                # Parse packet (with FEC support)
                parsed = self.protocol.parse_packet_fec(data)
                if not parsed:
                    continue
                
                # Add packet to FEC decoder (both data and FEC packets)
                if self.fec_decoder:
                    try:
                        complete_block = self.fec_decoder.add_packet(data, parsed)
                    except Exception as e:
                        print(f"[ERROR] FEC decoder exception: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                    
                    if complete_block:
                        # FEC decoder returned a complete block - process ALL packets in order
                        print(f"\n[FEC] Block complete: {len(complete_block)} packet(s) ready")
                        
                        # Handle blocks with gaps (packets couldn't be recovered)
                        has_gaps = len(complete_block) < 10
                        if self.jitter_buffer and has_gaps:
                            # Block has gaps - reset state tracking to prevent stuck key
                            # Gaps mean we lost some state transitions
                            self.jitter_buffer.reset_state_tracking()
                            self.jitter_buffer.suppress_state_validation(True)
                        
                        for pkt in complete_block:
                            seq = pkt['sequence']
                            if seq not in self.processed_sequences:
                                self.processed_sequences.add(seq)
                                for key_down, duration_ms in pkt['events']:
                                    if self.jitter_buffer:
                                        self.jitter_buffer.add_event(key_down, duration_ms, receive_time)
                                    else:
                                        self._process_event(key_down, duration_ms, seq)
                        
                        # After processing a gapped block, re-enable state validation
                        if self.jitter_buffer and has_gaps:
                            self.jitter_buffer.suppress_state_validation(False)
                
                # Check if this is a FEC packet (don't count as data packet)
                if parsed.get('is_fec', False):
                    self.fec_packet_count += 1
                    continue
                
                self.packet_count += 1
                
                # Check for lost packets
                seq = parsed['sequence']
                if seq != 0xFF:  # Skip EOT and padding
                    time_gap = receive_time - self.last_packet_time if self.last_packet_time > 0 else 0
                    
                    if self.last_sequence >= 0 and seq != 0xFF:
                        expected = (self.last_sequence + 1) % 256
                        if seq != expected:
                            lost = (seq - expected) % 256
                            
                            if time_gap > 2.0:
                                print(f"\n[INFO] New transmission detected")
                            elif lost >= 100:
                                if self.debug:
                                    print(f"\n[DEBUG] Sequence wrap: {self.last_sequence}→{seq}")
                            else:
                                self.lost_packets += lost
                                print(f"\n[WARNING] Lost {lost} packet(s) - expected {expected}, got {seq}")
                                
                                # FEC will try to recover these
                                if self.protocol.fec_enabled:
                                    print(f"[FEC] Will attempt recovery...")
                    
                    self.last_sequence = seq
                    self.last_packet_time = receive_time
                
                # Check for EOT
                if parsed.get('eot', False):
                    print(f"\n[EOT] Transmission complete")
                    
                    # Flush any incomplete FEC blocks
                    if self.fec_decoder:
                        remaining_packets = self.fec_decoder.flush_incomplete_blocks()
                        if remaining_packets:
                            print(f"[FEC] Flushed {len(remaining_packets)} packet(s) from incomplete block(s)")
                            for pkt in remaining_packets:
                                seq = pkt['sequence']
                                if seq not in self.processed_sequences:
                                    self.processed_sequences.add(seq)
                                    for key_down, duration_ms in pkt['events']:
                                        if self.jitter_buffer:
                                            self.jitter_buffer.add_event(key_down, duration_ms, receive_time)
                                        else:
                                            self._process_event(key_down, duration_ms, seq)
                    
                    if self.jitter_buffer:
                        self.jitter_buffer.drain_buffer(timeout=2.0)
                    # Clear processed sequences for next transmission
                    self.processed_sequences.clear()
                    continue
                
                # If FEC is disabled, process packets immediately
                # If FEC is enabled, packets are only processed when FEC decoder releases a complete block
                if not self.fec_decoder:
                    seq = parsed['sequence']
                    for key_down, duration_ms in parsed['events']:
                        if self.jitter_buffer:
                            self.jitter_buffer.add_event(key_down, duration_ms, receive_time)
                        else:
                            self._process_event(key_down, duration_ms, seq)
        
        except KeyboardInterrupt:
            print("\n\nInterrupted")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup and show statistics"""
        if self.jitter_buffer:
            self.jitter_buffer.stop()
        
        if self.sidetone:
            self.sidetone.close()
        
        self.socket.close()
        
        print("\n" + "=" * 60)
        print("Session Statistics:")
        print("=" * 60)
        
        stats = self.stats.get_stats()
        print(f"Total data packets received: {self.packet_count}")
        print(f"Total FEC packets received: {self.fec_packet_count}")
        print(f"Packets lost: {self.lost_packets}")
        print(f"Packets recovered by FEC: {self.recovered_packets}")
        
        if self.packet_count > 0:
            loss_rate = (self.lost_packets / (self.packet_count + self.lost_packets)) * 100
            recovery_rate = (self.recovered_packets / max(1, self.lost_packets)) * 100
            print(f"Packet loss rate: {loss_rate:.2f}%")
            print(f"FEC recovery rate: {recovery_rate:.1f}%")
            
            if loss_rate > 0 and recovery_rate > 80:
                print(f"\n✓ FEC working well - recovered most losses!")
            elif loss_rate > 10:
                print(f"\n⚠️  HIGH PACKET LOSS - FEC may not be sufficient")
        
        print(f"\nTotal events: {stats.get('total_events', 0)}")
        print(f"Session duration: {stats.get('duration_sec', 0):.1f}s")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CW Protocol Receiver with FEC')
    parser.add_argument('--port', type=int, default=UDP_PORT, help='UDP port (default: 7355)')
    parser.add_argument('--jitter-buffer', type=int, default=150, 
                       help='Jitter buffer size in ms (default: 150ms for FEC, use 0 to disable)')
    parser.add_argument('--no-audio', action='store_true', help='Disable audio sidetone')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug output')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW Protocol Receiver with FEC")
    print("=" * 60)
    
    if args.jitter_buffer > 0:
        print(f"\n💡 Jitter buffer: {args.jitter_buffer}ms (required for FEC recovery)")
        print("   FEC packets arrive after data packets, buffer allows time for recovery")
    else:
        print(f"\n⚠️  WARNING: Jitter buffer disabled!")
        print("   FEC recovery may not work properly without buffering")
    
    print()
    
    if args.debug:
        print("🐛 DEBUG MODE ENABLED\n")
    
    receiver = CWReceiverFEC(args.port, enable_audio=not args.no_audio, 
                            jitter_buffer_ms=args.jitter_buffer, debug=args.debug)
    receiver.run()
