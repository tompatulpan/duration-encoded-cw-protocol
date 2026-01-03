#!/usr/bin/env python3
"""
Test UDP Timestamp Receiver - Using modular protocol structure
"""

import sys
import os
import time
import argparse

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol.udp_ts import CWProtocolUDPTimestamp, UDP_TS_PORT
from protocol.stats import CWTimingStats
from buffer.jitter import JitterBuffer
from audio.sidetone import SidetoneGenerator

def main():
    parser = argparse.ArgumentParser(description='Test UDP+TS CW Receiver (modular)')
    parser.add_argument('--port', type=int, default=UDP_TS_PORT, help=f'UDP port (default: {UDP_TS_PORT})')
    parser.add_argument('--jitter-buffer', type=int, default=150, help='Jitter buffer in ms (default: 150ms for WiFi)')
    parser.add_argument('--no-audio', action='store_true', help='Disable audio sidetone')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    # Create protocol handler
    protocol = CWProtocolUDPTimestamp()
    protocol.create_socket(args.port)
    protocol.sock.settimeout(0.1)  # 100ms timeout for clean shutdown
    
    # Create statistics tracker
    stats = CWTimingStats()
    
    # Create audio sidetone (if enabled)
    sidetone = None
    if not args.no_audio:
        try:
            sidetone = SidetoneGenerator(frequency=700)  # 700 Hz for RX
            print("[AUDIO] Sidetone enabled at 700 Hz")
        except Exception as e:
            print(f"[AUDIO] Warning: Could not initialize audio: {e}")
            print("[AUDIO] Continuing without audio (visual only)")
    
    # Create jitter buffer
    jitter_buffer = JitterBuffer(args.jitter_buffer)
    jitter_buffer.debug = args.debug
    print(f"[BUFFER] Jitter buffer: {args.jitter_buffer}ms (timestamp-based scheduling)")
    
    # Playout callback
    def handle_event(key_down, duration_ms):
        """Handle CW event (audio + visual)"""
        if sidetone:
            sidetone.set_key(key_down)
        
        # Visual feedback
        state = "■" if key_down else "·"
        sys.stdout.write(state)
        sys.stdout.flush()
        
        # Track statistics
        stats.add_event(key_down, duration_ms)
    
    # Start jitter buffer
    jitter_buffer.start(handle_event)
    
    # Synchronization state
    sender_timeline_offset = None  # Time offset between sender and receiver clocks
    last_sender_addr = None
    
    print(f"\n[TEST] UDP Timestamp Receiver listening on port {args.port}")
    print("[TEST] Using MODULAR protocol structure")
    print("[TEST] Protocol: UDP with timestamps (burst-resistant)")
    print("-" * 60)
    print("Waiting for packets...\n")
    
    packet_count = 0
    
    try:
        while True:
            result = protocol.recv_packet()
            
            if result is None:
                continue
            
            key_down, duration_ms, timestamp_ms, sender_addr = result
            
            # Track new sender
            if last_sender_addr != sender_addr:
                if last_sender_addr is not None:
                    print(f"\n[NEW SENDER] {sender_addr[0]}:{sender_addr[1]}")
                else:
                    print(f"[CONNECTED] First packet from {sender_addr[0]}:{sender_addr[1]}")
                last_sender_addr = sender_addr
                sender_timeline_offset = None  # Reset timeline sync
            
            # Check for EOT
            if key_down == 'EOT':
                print("\n[EOT] End of transmission")
                jitter_buffer.drain_buffer()
                
                # Show buffer statistics
                print("\n[BUFFER] Statistics:")
                buffer_stats = jitter_buffer.get_stats()
                for key, value in buffer_stats.items():
                    if isinstance(value, float):
                        print(f"  {key}: {value:.1f}")
                    else:
                        print(f"  {key}: {value}")
                print()
                
                # Reset for next transmission
                sender_timeline_offset = None
                jitter_buffer.reset_connection("EOT")
                continue
            
            packet_count += 1
            
            # Synchronize timeline on first packet
            if sender_timeline_offset is None:
                sender_timeline_offset = time.time() - (timestamp_ms / 1000.0)
                if args.debug:
                    print(f"[DEBUG] Timeline synchronized: offset = {sender_timeline_offset:.3f}s")
            
            # Calculate sender's event time in our clock
            sender_event_time = sender_timeline_offset + (timestamp_ms / 1000.0)
            
            # Calculate scheduling delay
            now = time.time()
            playout_time = sender_event_time + (args.jitter_buffer / 1000.0)
            delay_to_playout = (playout_time - now) * 1000
            
            if args.debug:
                state_str = "DOWN" if key_down else "UP"
                print(f"[DEBUG] TS-based scheduling: {delay_to_playout:.1f}ms from now")
            
            # Add to jitter buffer with timestamp-based scheduling
            jitter_buffer.add_event_ts(key_down, duration_ms, sender_event_time)
    
    except KeyboardInterrupt:
        print("\n\n[TEST] Stopping receiver...")
    
    finally:
        # Cleanup
        jitter_buffer.stop()
        if sidetone:
            sidetone.close()
        protocol.close()
        
        # Print statistics
        print("\n" + "=" * 60)
        print("RECEPTION STATISTICS")
        print("=" * 60)
        print(f"Packets received: {protocol.packets_received}")
        print(f"Packets lost: {protocol.packets_lost}")
        if protocol.packets_received > 0:
            loss_rate = (protocol.packets_lost / (protocol.packets_received + protocol.packets_lost)) * 100
            print(f"Loss rate: {loss_rate:.1f}%")
        
        timing_stats = stats.get_stats()
        if timing_stats.get('total_events', 0) > 0:
            print(f"\nTotal events: {timing_stats['total_events']}")
            print("\nTIMING ANALYSIS")
            print("-" * 60)
            if 'avg_dit_ms' in timing_stats:
                print(f"Average dit: {timing_stats['avg_dit_ms']:.1f}ms")
                print(f"Estimated WPM: {timing_stats.get('wpm', 0):.1f}")
            if 'avg_dah_ms' in timing_stats:
                print(f"Average dah: {timing_stats['avg_dah_ms']:.1f}ms")
        print("=" * 60)
        print("[TEST] Receiver stopped")
    
    return 0

if __name__ == '__main__':
    exit(main())
