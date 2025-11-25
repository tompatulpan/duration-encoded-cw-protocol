#!/usr/bin/env python3
"""
CW Receiver with Automatic Packet Loss Recovery

Demonstrates interpolation-based FEC for transparent packet loss recovery.
Use this instead of cw_receiver.py when on lossy networks.

Usage:
  python3 cw_receiver_fec.py [--port PORT] [--jitter-buffer MS] [--interpolate]
  
Example:
  python3 cw_receiver_fec.py --jitter-buffer 100 --interpolate
"""

import sys
import socket
import time
import argparse
from cw_protocol import CWProtocol
from cw_receiver import CWReceiver
from cw_fec import FECReceiver

class CWReceiverWithFEC(CWReceiver):
    """CW Receiver with packet loss interpolation"""
    
    def __init__(self, port=7355, enable_audio=True, jitter_buffer_ms=0, enable_interpolation=True):
        super().__init__(port, enable_audio, jitter_buffer_ms)
        
        self.enable_interpolation = enable_interpolation
        self.fec_receiver = FECReceiver(fec_mode='none')
        self.recent_packets = []  # For interpolation context
        self.interpolated_count = 0
        
    def run(self):
        """Main receive loop with interpolation"""
        # Start jitter buffer playout thread if enabled
        if self.jitter_buffer:
            self.jitter_buffer.start(lambda kd, dur: self._process_event(kd, dur))
        
        print(f"CW Receiver listening on port {self.port}")
        
        if self.sidetone:
            print(f"Audio sidetone enabled (700 Hz)")
        else:
            print("Audio sidetone disabled (PyAudio not available)")
        
        if self.jitter_buffer:
            print(f"Jitter buffer enabled ({self.jitter_buffer.buffer_ms}ms) for WAN use")
        
        if self.enable_interpolation:
            print("✓ Packet loss interpolation ENABLED")
        
        print(f"Statistics will update every 10 packets")
        print("-" * 60)
        
        try:
            while True:
                # Receive packet
                packet_bytes, addr = self.socket.recvfrom(1024)
                receive_time = time.time()
                
                # Parse packet
                parsed = self.protocol.parse_packet(packet_bytes)
                if not parsed:
                    continue
                
                self.packet_count += 1
                
                # Check for lost packets
                seq = parsed['sequence']
                time_gap = receive_time - self.last_packet_time if self.last_packet_time > 0 else 0
                
                if self.last_sequence >= 0:
                    expected = (self.last_sequence + 1) % 256
                    if seq != expected:
                        lost = (seq - expected) % 256
                        
                        # Detect new transmission vs packet loss
                        if time_gap > 2.0:
                            print(f"\n[INFO] New transmission detected (silence: {time_gap:.1f}s)")
                        elif lost > 128 and seq < 10:
                            print(f"\n[INFO] Sequence reset: expected {expected}, got {seq} (new transmission)")
                        else:
                            # Real packet loss - try to interpolate
                            if self.enable_interpolation and lost <= 2:
                                interpolated = self.fec_receiver.interpolate_missing(
                                    self.last_sequence,
                                    seq,
                                    self.recent_packets[-5:],
                                    packet_bytes
                                )
                                
                                if interpolated:
                                    print(f"\n[FEC] Interpolated {len(interpolated)} missing packet(s) between seq {self.last_sequence} and {seq}")
                                    self.interpolated_count += len(interpolated)
                                    
                                    # Process interpolated packets
                                    for ipkt in interpolated:
                                        iparsed = self.protocol.parse_packet(ipkt)
                                        if iparsed and iparsed['events']:
                                            for key_down, duration_ms in iparsed['events']:
                                                if self.jitter_buffer:
                                                    self.jitter_buffer.add_event(key_down, duration_ms, receive_time)
                                                else:
                                                    self._process_event(key_down, duration_ms, iparsed['sequence'])
                            else:
                                # Cannot interpolate - report loss
                                self.lost_packets += lost
                                print(f"\n[WARNING] Lost {lost} packet(s) - expected {expected}, got {seq}")
                
                self.last_sequence = seq
                self.last_packet_time = receive_time
                
                # Check for End-of-Transmission
                if parsed.get('eot', False):
                    print(f"\n[EOT] Transmission complete, draining buffer...")
                    if self.jitter_buffer:
                        self.jitter_buffer.drain_buffer(timeout=2.0)
                    print("[EOT] Buffer drained")
                    continue
                
                # Process events from received packet
                for key_down, duration_ms in parsed['events']:
                    if self.jitter_buffer:
                        self.jitter_buffer.add_event(key_down, duration_ms, receive_time)
                    else:
                        self._process_event(key_down, duration_ms, seq)
                
                # Keep packet history for interpolation
                self.recent_packets.append(packet_bytes)
                if len(self.recent_packets) > 10:
                    self.recent_packets.pop(0)
                
        except KeyboardInterrupt:
            print("\n\nInterrupted")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup and show statistics including interpolation stats"""
        # Call parent cleanup
        super().cleanup()
        
        # Show interpolation stats
        if self.enable_interpolation and self.interpolated_count > 0:
            print(f"\nPacket Loss Recovery:")
            print(f"  Interpolated packets: {self.interpolated_count}")
            total = self.packet_count + self.interpolated_count
            interp_rate = (self.interpolated_count / total) * 100 if total > 0 else 0
            print(f"  Interpolation rate: {interp_rate:.1f}% of total")

def main():
    parser = argparse.ArgumentParser(
        description='CW Protocol Receiver with Packet Loss Recovery (FEC)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic receiver with interpolation
  python3 cw_receiver_fec.py --interpolate
  
  # With jitter buffer for internet use
  python3 cw_receiver_fec.py --jitter-buffer 100 --interpolate
  
  # Without interpolation (standard receiver)
  python3 cw_receiver_fec.py --no-interpolate

Interpolation automatically reconstructs missing packets based on CW patterns.
Best for networks with < 30% packet loss.
        """
    )
    
    parser.add_argument('--port', type=int, default=7355,
                       help='UDP port to listen on (default: 7355)')
    parser.add_argument('--no-audio', action='store_true',
                       help='Disable audio sidetone')
    parser.add_argument('--jitter-buffer', type=int, default=0, metavar='MS',
                       help='Enable jitter buffer with size in milliseconds (0=disabled)')
    parser.add_argument('--interpolate', dest='interpolate', action='store_true', default=True,
                       help='Enable packet loss interpolation (default)')
    parser.add_argument('--no-interpolate', dest='interpolate', action='store_false',
                       help='Disable packet loss interpolation')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW Protocol Receiver with FEC")
    print("=" * 60)
    print()
    
    if args.jitter_buffer > 0:
        print(f"💡 WAN Mode: Jitter buffer enabled ({args.jitter_buffer}ms)")
        print(f"   This smooths out internet latency variations")
        print(f"   Note: Adds {args.jitter_buffer}ms of intentional delay")
        print()
    
    if args.interpolate:
        print(f"💡 FEC Mode: Packet loss interpolation enabled")
        print(f"   Missing packets will be reconstructed from CW patterns")
        print(f"   Best for networks with < 30% packet loss")
        print()
    
    # Create and run receiver
    receiver = CWReceiverWithFEC(
        port=args.port,
        enable_audio=not args.no_audio,
        jitter_buffer_ms=args.jitter_buffer,
        enable_interpolation=args.interpolate
    )
    
    receiver.run()

if __name__ == '__main__':
    main()
