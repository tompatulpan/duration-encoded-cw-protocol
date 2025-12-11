#!/usr/bin/env python3
"""
CW Receiver TCP - Listen for CW keying events over TCP and generate sidetone
"""

import sys
import time
import threading
from cw_protocol_tcp import CWServerTCP, TCP_PORT
from cw_protocol import CWTimingStats

# Audio support (optional) - reuse from UDP version
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: pyaudio not available, audio sidetone disabled")
    print("Install with: pip3 install pyaudio")

# Import jitter buffer from UDP version
try:
    from cw_receiver import JitterBuffer, SidetoneGenerator
except ImportError:
    print("Warning: Could not import JitterBuffer/SidetoneGenerator from cw_receiver.py")
    JitterBuffer = None
    SidetoneGenerator = None


class CWReceiverTCP:
    def __init__(self, port=TCP_PORT, enable_audio=True, jitter_buffer_ms=0, debug=False):
        self.port = port
        self.jitter_buffer_ms = jitter_buffer_ms
        self.debug = debug
        
        # TCP server
        self.server = CWServerTCP(port=port)
        self.stats = CWTimingStats()
        
        # Audio sidetone
        self.sidetone = None
        if enable_audio and AUDIO_AVAILABLE and SidetoneGenerator:
            self.sidetone = SidetoneGenerator(frequency=700)  # 700 Hz for RX
        
        # Jitter buffer (optional, for internet/WAN use)
        self.jitter_buffer = None
        if jitter_buffer_ms > 0 and JitterBuffer:
            self.jitter_buffer = JitterBuffer(jitter_buffer_ms)
            self.jitter_buffer.debug = debug
        
        self.last_sequence = -1
        self.packet_count = 0
        self.lost_packets = 0
        self.last_packet_time = 0
        self.stats_update_counter = 0
        
        print(f"CW Receiver TCP listening on port {port}")
        if self.sidetone:
            print("Audio sidetone enabled (700 Hz)")
        else:
            print("Audio sidetone disabled (visual only)")
        if self.jitter_buffer:
            print(f"Jitter buffer enabled ({jitter_buffer_ms}ms) for WAN use")
            print("Statistics will update every 10 packets")
        else:
            print("Jitter buffer disabled (LAN mode)")
        print("-" * 60)
    
    def _show_stats(self):
        """Display jitter buffer statistics"""
        if not self.jitter_buffer:
            return
        
        stats = self.jitter_buffer.get_stats()
        if 'delay_min' not in stats:
            return
        
        print("\n" + "=" * 60)
        print("NETWORK STATISTICS")
        print("=" * 60)
        print(f"Buffer size:      {stats['buffer_ms']}ms")
        print(f"Max delay seen:   {stats['buffer_used']:.1f}ms ({stats['buffer_used']/stats['buffer_ms']*100:.0f}% of buffer)")
        print(f"Min delay seen:   {stats['delay_min']:.1f}ms")
        print(f"Avg delay:        {stats['delay_avg']:.1f}ms (arrival-to-playout)")
        print(f"Timeline shifts:  {stats['timeline_shifts']}")
        
        # Show shift breakdown
        gap_shifts = stats['timeline_shifts_after_gap']
        network_shifts = stats['timeline_shifts'] - gap_shifts
        if gap_shifts > 0:
            print(f"  - After gaps:   {gap_shifts} (manual keying pauses)")
        if network_shifts > 0:
            print(f"  - Network:      {network_shifts} (actual jitter)")
        
        print(f"Max queue depth:  {stats['max_queue_depth']}")
        print(f"Current queue:    {stats['queued_events']}")
        print(f"Samples:          {stats['samples']}")
        
        # Recommendations
        usage_percent = (stats['buffer_used'] / stats['buffer_ms']) * 100
        network_jitter_rate = network_shifts / max(1, stats['samples'])
        
        if network_jitter_rate > 0.2:
            print(f"\n⚠️  RECOMMENDATION: Increase buffer to {stats['buffer_ms'] + 50}ms (high network jitter)")
        elif usage_percent >= 98:
            print(f"\n⚠️  RECOMMENDATION: Increase buffer to {stats['buffer_ms'] + 20}ms (hitting ceiling)")
        elif usage_percent < 60 and gap_shifts == stats['timeline_shifts']:
            suggested = max(20, int(stats['buffer_used'] * 1.3))
            print(f"\n✓ Buffer larger than needed - could reduce to ~{suggested}ms")
        else:
            print(f"\n✓ Buffer size looks good!")
        
        print("=" * 60 + "\n")
    
    def _process_event(self, key_down, duration_ms, seq=0):
        """Process a CW event (called directly or from jitter buffer)"""
        # Record for statistics
        self.stats.add_event(key_down, duration_ms)
        
        # Debug timing
        if self.debug:
            state_name = "DOWN" if key_down else "UP  "
            print(f"\n[PLAY] {state_name} for {duration_ms}ms at {time.time():.3f}")
        
        # Update audio sidetone
        if self.sidetone:
            self.sidetone.set_key(key_down)
        
        # Periodically show statistics (every 10 packets)
        if self.jitter_buffer and self.packet_count % 10 == 0:
            self.stats_update_counter += 1
            if self.stats_update_counter >= 3:  # Every 30 packets
                self._show_stats()
                self.stats_update_counter = 0
        
        # Visual feedback
        state_str = "█" * 40 if key_down else " " * 40
        status = "DOWN" if key_down else "UP  "
        
        jitter_info = ""
        if self.jitter_buffer:
            jitter_stats = self.jitter_buffer.get_stats()
            jitter_info = f" JBuf:{jitter_stats['queued_events']:2d}"
        
        print(f"\r[{state_str}] {status} {duration_ms:4d}ms | "
              f"Seq:{seq:3d} Pkts:{self.packet_count:4d} "
              f"Lost:{self.lost_packets:2d}{jitter_info}",
              end='', flush=True)
    
    def run(self):
        """Main receive loop"""
        # Start TCP server
        if not self.server.start():
            print("[TCP] Failed to start server")
            return
        
        print(f"[TCP] Server started, waiting for connection...")
        
        # Start jitter buffer playout thread if enabled
        if self.jitter_buffer:
            self.jitter_buffer.start(lambda kd, dur: self._process_event(kd, dur))
        
        try:
            while True:
                # Wait for incoming connection
                if not self.server.accept_connection(timeout=1.0):
                    continue
                
                print(f"[TCP] Client connected from {self.server.client_addr}")
                
                # Reset counters for new connection
                self.last_sequence = -1
                self.packet_count = 0
                self.lost_packets = 0
                self.last_packet_time = 0
                
                # Reset jitter buffer state for new connection
                if self.jitter_buffer:
                    self.jitter_buffer.reset_state_tracking()
                    # Clear any stale events from previous connection
                    while not self.jitter_buffer.event_queue.empty():
                        try:
                            self.jitter_buffer.event_queue.get_nowait()
                        except:
                            break
                
                # Receive packets from this client
                while True:
                    # Receive packet
                    parsed = self.server.recv_packet(timeout=5.0)
                    
                    if parsed is None:
                        # Timeout or connection closed
                        if not self.server.protocol.is_connected():
                            print(f"\n[TCP] Client disconnected")
                            
                            # Reset jitter buffer state for clean restart
                            if self.jitter_buffer:
                                # Wait for buffer to drain
                                self.jitter_buffer.drain_buffer(timeout=2.0)
                                # Reset state tracking completely
                                self.jitter_buffer.reset_state_tracking()
                                # Clear any remaining events
                                while not self.jitter_buffer.event_queue.empty():
                                    try:
                                        self.jitter_buffer.event_queue.get_nowait()
                                    except:
                                        break
                            
                            self.server.close_client()
                            break
                        continue
                    
                    receive_time = time.time()
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
                            elif lost >= 100:
                                # Sequence wrap or reset
                                if self.debug:
                                    print(f"\n[DEBUG] Sequence wrap: {self.last_sequence}→{seq}")
                            else:
                                # Real packet loss
                                self.lost_packets += lost
                                print(f"\n[WARNING] Lost {lost} packet(s) - expected {expected}, got {seq}")
                    
                    self.last_sequence = seq
                    self.last_packet_time = receive_time
                    
                    # Check for End-of-Transmission
                    if parsed.get('eot', False):
                        print(f"\n[EOT] Transmission complete, draining buffer...", flush=True)
                        if self.jitter_buffer:
                            self.jitter_buffer.drain_buffer(timeout=2.0)
                            print("[EOT] Buffer drained and reset", flush=True)
                        else:
                            print("[EOT] No buffer to drain", flush=True)
                        continue
                    
                    # Process events
                    for key_down, duration_ms in parsed['events']:
                        if self.jitter_buffer:
                            # Add to jitter buffer for delayed playout
                            self.jitter_buffer.add_event(key_down, duration_ms, receive_time)
                        else:
                            # Immediate playout (LAN mode)
                            self._process_event(key_down, duration_ms, seq)
                
                # Client disconnected, wait for next connection
                print(f"[TCP] Waiting for next connection...")
                
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
        
        self.server.stop()
        
        print("\n" + "=" * 60)
        print("Session Statistics:")
        print("=" * 60)
        
        # Show state validation errors if any
        if self.jitter_buffer and self.jitter_buffer.state_errors > 0:
            print(f"\n⚠️  STATE ERRORS: {self.jitter_buffer.state_errors}")
            print("   Protocol violation - DOWN/UP events not alternating properly")
            print("   This may indicate sender bug or packet reordering\n")
        
        stats = self.stats.get_stats()
        print(f"Total packets received: {self.packet_count}")
        print(f"Packets lost: {self.lost_packets}")
        
        if self.packet_count > 0:
            loss_rate = (self.lost_packets / (self.packet_count + self.lost_packets)) * 100
            print(f"Packet loss rate: {loss_rate:.2f}%")
            
            if loss_rate > 10:
                print(f"\n⚠️  HIGH PACKET LOSS!")
                print("Note: TCP should not lose packets (connection-based)")
                print("This indicates sender disconnections or network issues")
            elif loss_rate > 1:
                print(f"\n⚠️  Moderate packet loss - unusual for TCP")
            else:
                print(f"\n✓ Excellent - minimal packet loss!")
        
        print(f"\nTotal events: {stats.get('total_events', 0)}")
        print(f"Session duration: {stats.get('duration_sec', 0):.1f}s")
        
        if 'avg_dit_ms' in stats:
            print(f"\nTiming Analysis:")
            print(f"  Average dit: {stats['avg_dit_ms']:.1f}ms ({stats['dit_count']} dits)")
            if 'avg_dah_ms' in stats:
                print(f"  Average dah: {stats['avg_dah_ms']:.1f}ms ({stats['dah_count']} dahs)")
                print(f"  Dah/Dit ratio: {stats['dah_dit_ratio']:.2f} (ideal: 3.0)")
            if 'avg_space_ms' in stats:
                print(f"  Average space: {stats['avg_space_ms']:.1f}ms ({stats['space_count']} spaces)")
            print(f"  Estimated speed: {stats['wpm']:.1f} WPM")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='CW Protocol Receiver - TCP Version')
    parser.add_argument('--port', type=int, default=TCP_PORT, help='TCP port (default: 7355)')
    parser.add_argument('--jitter-buffer', type=int, default=0, 
                       help='Jitter buffer size in ms (0=disabled, recommend 50-200 for WAN)')
    parser.add_argument('--no-audio', action='store_true', help='Disable audio sidetone')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug output')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW Protocol Receiver - TCP Version")
    print("=" * 60)
    
    if args.jitter_buffer > 0:
        print(f"\n💡 WAN Mode: Jitter buffer enabled ({args.jitter_buffer}ms)")
        print("   This smooths out internet latency variations")
        print(f"   Note: Adds {args.jitter_buffer}ms of intentional delay")
    else:
        print(f"\n💡 LAN Mode: Direct playout (no buffering)")
        print("   For internet use, try: --jitter-buffer 100")
    print()
    
    if args.debug:
        print("🐛 DEBUG MODE ENABLED - Verbose timing output\n")
    
    # Check if jitter buffer is available
    if args.jitter_buffer > 0 and JitterBuffer is None:
        print("⚠️  WARNING: JitterBuffer not available (cw_receiver.py import failed)")
        print("   Falling back to direct playout mode\n")
        args.jitter_buffer = 0
    
    receiver = CWReceiverTCP(args.port, enable_audio=not args.no_audio, 
                             jitter_buffer_ms=args.jitter_buffer, debug=args.debug)
    receiver.run()
