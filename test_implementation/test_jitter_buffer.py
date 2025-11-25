#!/usr/bin/env python3
"""
Test script to demonstrate jitter buffer effect
Simulates network jitter by adding random delays to packets
"""

import socket
import time
import random
import sys
from cw_protocol import CWProtocol, UDP_PORT

def send_with_jitter(host, port, wpm=20, jitter_ms=50):
    """
    Send CW pattern with simulated network jitter
    
    Args:
        host: Target hostname/IP
        port: UDP port
        wpm: Words per minute
        jitter_ms: Maximum random jitter to add (milliseconds)
    """
    protocol = CWProtocol()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Calculate timing for given WPM
    # Standard: 1 dit = 1.2 / WPM seconds
    dit_ms = int(1200 / wpm)
    dah_ms = dit_ms * 3
    space_ms = dit_ms
    
    print(f"Sending test pattern to {host}:{port}")
    print(f"Speed: {wpm} WPM (dit={dit_ms}ms)")
    print(f"Simulated jitter: 0-{jitter_ms}ms")
    print("-" * 60)
    
    # Send "SOS" pattern: ... --- ...
    pattern = [
        ('S', [dit_ms, space_ms, dit_ms, space_ms, dit_ms, space_ms * 3]),  # ...
        ('O', [dah_ms, space_ms, dah_ms, space_ms, dah_ms, space_ms * 3]),  # ---
        ('S', [dit_ms, space_ms, dit_ms, space_ms, dit_ms, space_ms * 7]),  # ...
    ]
    
    seq = 0
    
    for char, timings in pattern:
        print(f"\nSending '{char}'...")
        
        for i, duration in enumerate(timings):
            is_key_down = (i % 2 == 0)  # Even indices are key-down
            
            # Create packet
            packet = protocol.create_packet(is_key_down, duration, sequence=seq)
            seq = (seq + 1) % 256
            
            # Add random jitter delay (0 to jitter_ms)
            jitter = random.randint(0, jitter_ms)
            time.sleep(jitter / 1000.0)
            
            # Send packet
            sock.sendto(packet, (host, port))
            
            status = "█ DOWN" if is_key_down else "  UP"
            print(f"  {status} {duration:3d}ms (jitter: +{jitter:2d}ms)")
            
            # Wait for the event duration
            time.sleep(duration / 1000.0)
    
    sock.close()
    print("\n" + "=" * 60)
    print("Test complete!")
    print("\nWithout jitter buffer: You should hear timing variations")
    print("With jitter buffer:    Timing should be smooth and consistent")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test CW jitter buffer')
    parser.add_argument('--host', default='localhost', help='Target host (default: localhost)')
    parser.add_argument('--port', type=int, default=UDP_PORT, help='UDP port (default: 7355)')
    parser.add_argument('--wpm', type=int, default=20, help='Speed in WPM (default: 20)')
    parser.add_argument('--jitter', type=int, default=50, 
                       help='Max simulated jitter in ms (default: 50)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW Jitter Buffer Test")
    print("=" * 60)
    print()
    print("This script sends CW with simulated network jitter.")
    print()
    print("To test:")
    print("  1. Start receiver WITHOUT jitter buffer:")
    print("     python3 cw_receiver.py")
    print("     → You should hear uneven timing")
    print()
    print("  2. Start receiver WITH jitter buffer:")
    print("     python3 cw_receiver.py --jitter-buffer 100")
    print("     → Timing should be smooth")
    print()
    
    try:
        input("Press ENTER to start test (Ctrl+C to cancel)...")
    except KeyboardInterrupt:
        print("\nCancelled")
        sys.exit(0)
    
    send_with_jitter(args.host, args.port, args.wpm, args.jitter)
