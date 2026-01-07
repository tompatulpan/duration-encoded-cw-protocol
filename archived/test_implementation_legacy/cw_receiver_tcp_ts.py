#!/usr/bin/env python3
"""
CW Receiver TCP with Timestamps
Receives timestamped CW over TCP for burst-resistant timing
"""

import sys
import time
import argparse
from cw_protocol_tcp_ts import CWProtocolTCPTimestamp, TCP_PORT
from cw_receiver import JitterBuffer, SidetoneGenerator
from cw_protocol import CWTimingStats


def main():
    parser = argparse.ArgumentParser(description='CW Receiver TCP with Timestamps')
    parser.add_argument('--port', type=int, default=TCP_PORT, help='TCP port to listen on')
    parser.add_argument('--jitter-buffer', type=int, default=0, metavar='MS',
                       help='Jitter buffer size in milliseconds (0=disabled, 50-200 typical)')
    parser.add_argument('--no-audio', action='store_true', help='Disable audio sidetone')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print(f"CW Receiver TCP (with Timestamps) listening on port {args.port}")
    
    # Initialize audio sidetone
    sidetone = None
    if not args.no_audio:
        try:
            sidetone = SidetoneGenerator(frequency=700)  # 700 Hz for RX
            print("Audio sidetone enabled (700 Hz)")
        except Exception as e:
            print(f"Warning: Audio initialization failed: {e}")
    
    # Initialize jitter buffer
    jitter_buffer = None
    if args.jitter_buffer > 0:
        jitter_buffer = JitterBuffer(args.jitter_buffer)
        jitter_buffer.debug = args.debug  # Set debug flag separately
        use_type = "WAN" if args.jitter_buffer >= 100 else "LAN"
        print(f"Jitter buffer enabled ({args.jitter_buffer}ms) for {use_type} use")
        print(f"Statistics will update every 10 packets")
    else:
        print("Direct mode (no jitter buffer)")
    
    print("-" * 60)
    
    # Statistics tracking
    stats = CWTimingStats()
    packet_count = 0
    last_state = None
    state_errors = 0
    suppress_state_errors = False
    current_timestamp_ms = None  # Track current packet timestamp for debug display
    
    # Timestamp synchronization
    sender_timeline_offset = None  # sender_start_time in receiver's clock
    
    def playout_callback(key_down, duration_ms):
        """Callback for jitter buffer playout"""
        nonlocal last_state, state_errors, suppress_state_errors, packet_count, current_timestamp_ms
        
        # State validation
        if last_state is not None and last_state == key_down:
            state_errors += 1
            if not suppress_state_errors:
                expected = "UP" if key_down else "DOWN"
                got = "DOWN" if key_down else "UP"
                print(f"\n[ERROR] Invalid state: expected {expected}, got {got} (count: {state_errors})")
                if state_errors >= 5:
                    print("[ERROR] Suppressing further state errors...")
                    suppress_state_errors = True
        
        last_state = key_down
        
        # Audio feedback
        if sidetone:
            sidetone.set_key(key_down)
        
        # Debug output with timestamp
        if args.debug:
            state_str = "DOWN" if key_down else "UP"
            if current_timestamp_ms is not None:
                print(f"[PLAY] {state_str} {duration_ms}ms (ts={current_timestamp_ms}ms)")
            else:
                print(f"[PLAY] {state_str} {duration_ms}ms")
        
        # Statistics
        stats.add_event(key_down, duration_ms)
        if packet_count % 10 == 0 and packet_count > 0:
            stats_data = stats.get_stats()
            print(f"\n[STATS] Events: {stats_data.get('total_events', 0)}, " +
                  f"WPM: {stats_data.get('wpm', 0):.1f}")
            if jitter_buffer and hasattr(jitter_buffer, 'stats_max_queue'):
                print(f"[BUFFER] Max queue: {jitter_buffer.stats_max_queue}, " +
                      f"Current: {jitter_buffer.event_queue.qsize()}")
                      
    
    # Start jitter buffer if enabled
    if jitter_buffer:
        jitter_buffer.start(playout_callback)
    
    # Protocol handler
    protocol = CWProtocolTCPTimestamp()
    
    try:
        # Listen for connections
        if not protocol.listen(args.port):
            print(f"[TCP] Failed to start server on port {args.port}")
            return 1
        
        while True:
            print(f"[TCP] Server started, waiting for connection...")
            addr = protocol.accept()
            
            if not addr:
                continue
            
            print(f"[TCP] Client connected from {addr}")
            
            # Reset state for new connection
            if args.debug:
                print("\n[DEBUG] State tracking reset (new TCP connection)")
            last_state = None
            state_errors = 0
            suppress_state_errors = False
            sender_timeline_offset = None
            
            if jitter_buffer:
                jitter_buffer.reset_connection()
                print("[TCP] Buffer reset complete, ready for new transmission")
            
            # Receive packets from this connection
            while protocol.connected:
                if args.debug:
                    print("[DEBUG] Waiting for packet...")
                
                result = protocol.recv_packet()
                
                if args.debug:
                    print(f"[DEBUG] recv_packet returned: {result is not None}")
                
                if result is None:
                    # EOT or connection lost
                    break
                
                key_down, duration_ms, timestamp_ms = result
                
                # Store timestamp for debug display
                current_timestamp_ms = timestamp_ms
                
                if args.debug:
                    print(f"\n[DEBUG] Received timestamped packet: ts={timestamp_ms}ms")
                
                # Initialize sender timeline on first packet
                if sender_timeline_offset is None:
                    sender_timeline_offset = time.time() - (timestamp_ms / 1000.0)
                    if args.debug:
                        print(f"[DEBUG] Synchronized to sender timeline (offset: {sender_timeline_offset:.3f})")
                
                # Calculate absolute playout time from sender's timestamp
                sender_event_time = sender_timeline_offset + (timestamp_ms / 1000.0)
                
                if jitter_buffer:
                    # Add to jitter buffer with timestamp-based scheduling
                    # The jitter buffer will schedule relative to sender's timeline
                    jitter_buffer.add_event_ts(key_down, duration_ms, sender_event_time)
                else:
                    # Direct playback (immediate)
                    playout_callback(key_down, duration_ms)
                
                packet_count += 1
            
            # Connection closed
            print("\n[TCP] Client disconnected")
            
            if jitter_buffer:
                jitter_buffer.drain_buffer()
            
            if args.debug:
                print("[DEBUG] State tracking reset (client disconnected)")
            
            last_state = None
            sender_timeline_offset = None
            print("[TCP] Waiting for next connection...")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    
    finally:
        # Cleanup
        if jitter_buffer:
            jitter_buffer.stop()
        
        if sidetone:
            sidetone.close()
        
        protocol.close()
        
        # Print final statistics
        stats_data = stats.get_stats()
        print("\n" + "=" * 60)
        print("Session Statistics:")
        print("=" * 60)
        print(f"Total events: {stats_data.get('total_events', 0)}")
        print(f"Session duration: {stats_data.get('duration_sec', 0):.1f}s")
        
        if 'avg_dit_ms' in stats_data:
            print(f"\nTiming Analysis:")
            print(f"  Average dit: {stats_data['avg_dit_ms']:.1f}ms ({stats_data.get('dit_count', 0)} dits)")
            if 'avg_dah_ms' in stats_data:
                print(f"  Average dah: {stats_data['avg_dah_ms']:.1f}ms ({stats_data.get('dah_count', 0)} dahs)")
                print(f"  Dah/Dit ratio: {stats_data.get('dah_dit_ratio', 0):.2f} (ideal: 3.0)")
            if 'avg_space_ms' in stats_data:
                print(f"  Average space: {stats_data['avg_space_ms']:.1f}ms ({stats_data.get('space_count', 0)} spaces)")
            print(f"  Estimated speed: {stats_data.get('wpm', 0):.1f} WPM")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
