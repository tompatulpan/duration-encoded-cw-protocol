#!/usr/bin/env python3
"""
Test UDP Receiver - Using modular protocol structure
"""

import sys
import os
import time
import argparse

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol.udp import CWProtocolUDP
from protocol.stats import CWTimingStats
from buffer.jitter import JitterBuffer
from audio.sidetone import SidetoneGenerator

def main():
    parser = argparse.ArgumentParser(description='Test UDP CW Receiver (modular)')
    parser.add_argument('--port', type=int, default=7355, help='UDP port (default: 7355)')
    parser.add_argument('--jitter-buffer', type=int, default=0, help='Jitter buffer in ms (0=disabled)')
    parser.add_argument('--no-audio', action='store_true', help='Disable audio sidetone')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    # Create protocol handler
    protocol = CWProtocolUDP(port=args.port)
    protocol.bind()
    
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
    
    # Create jitter buffer (if enabled)
    jitter_buffer = None
    if args.jitter_buffer > 0:
        jitter_buffer = JitterBuffer(args.jitter_buffer)
        jitter_buffer.debug = args.debug
        print(f"[BUFFER] Jitter buffer enabled: {args.jitter_buffer}ms")
    
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
        
        # For non-buffered mode, simulate the duration
        if not jitter_buffer:
            time.sleep(duration_ms / 1000.0)
    
    # Start jitter buffer if enabled
    if jitter_buffer:
        jitter_buffer.start(handle_event)
    
    print(f"\n[TEST] UDP Receiver listening on port {args.port}")
    print("[TEST] Using MODULAR protocol structure")
    if jitter_buffer:
        print(f"[TEST] Mode: Buffered ({args.jitter_buffer}ms jitter buffer)")
    else:
        print("[TEST] Mode: Unbuffered (direct playout)")
    print("-" * 60)
    print("Receiving... (Ctrl+C to stop)\n")
    
    last_sequence = -1
    packet_count = 0
    lost_packets = 0
    
    try:
        while True:
            # Receive packet
            packet = protocol.recv_packet(timeout=1.0)
            if packet is None:
                continue
            
            packet_count += 1
            
            # Check for EOT
            if packet.get('eot'):
                print("\n[EOT] End of transmission")
                if jitter_buffer:
                    jitter_buffer.drain_buffer()
                    print("\n[BUFFER] Statistics:")
                    buffer_stats = jitter_buffer.get_stats()
                    for key, value in buffer_stats.items():
                        if isinstance(value, float):
                            print(f"  {key}: {value:.1f}")
                        else:
                            print(f"  {key}: {value}")
                print()
                continue
            
            # Track packet loss
            seq = packet['sequence']
            if last_sequence >= 0:
                expected_seq = (last_sequence + 1) % 256
                if seq != expected_seq:
                    lost = (seq - expected_seq) % 256
                    lost_packets += lost
                    print(f"\n[LOSS] {lost} packet(s) lost (seq {expected_seq} → {seq})")
            last_sequence = seq
            
            # Process events
            for key_down, duration_ms in packet['events']:
                arrival_time = time.time()
                
                if jitter_buffer:
                    # Add to jitter buffer for scheduled playout
                    jitter_buffer.add_event(key_down, duration_ms, arrival_time)
                else:
                    # Direct playout (no buffering)
                    handle_event(key_down, duration_ms)
    
    except KeyboardInterrupt:
        print("\n\n[TEST] Stopping receiver...")
    
    finally:
        # Cleanup
        if jitter_buffer:
            jitter_buffer.stop()
        if sidetone:
            sidetone.close()
        protocol.close()
        
        # Print statistics
        print("\n" + "=" * 60)
        print("RECEPTION STATISTICS")
        print("=" * 60)
        print(f"Packets received: {packet_count}")
        print(f"Packets lost: {lost_packets}")
        if packet_count > 0:
            loss_rate = (lost_packets / (packet_count + lost_packets)) * 100
            print(f"Loss rate: {loss_rate:.1f}%")
        
        timing_stats = stats.get_stats()
        if timing_stats.get('total_events', 0) > 0:
            print("\nTIMING ANALYSIS")
            print("-" * 60)
            if 'avg_dit_ms' in timing_stats:
                print(f"Average dit: {timing_stats['avg_dit_ms']:.1f}ms")
                print(f"Estimated WPM: {timing_stats.get('wpm', 0):.1f}")
            if 'avg_dah_ms' in timing_stats:
                print(f"Average dah: {timing_stats['avg_dah_ms']:.1f}ms")
        print("=" * 60)
        print("[TEST] Receiver stopped")

if __name__ == '__main__':
    main()
