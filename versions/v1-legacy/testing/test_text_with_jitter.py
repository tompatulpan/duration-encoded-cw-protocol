#!/usr/bin/env python3
"""
Test CW transmission with jitter simulation
Sends "PARIS" with optional network jitter
"""
import time
import socket
import random
from cw_protocol import CWProtocol, UDP_PORT

# Morse code definitions (dit=48ms, dah=144ms at 25 WPM)
MORSE_CODE = {
    'P': [(True, 48), (False, 48), (True, 144), (False, 48), (True, 144), (False, 48), (True, 48), (False, 144)],  # .--. 
    'A': [(True, 48), (False, 48), (True, 144), (False, 144)],  # .-
    'R': [(True, 48), (False, 48), (True, 144), (False, 48), (True, 48), (False, 144)],  # .-.
    'I': [(True, 48), (False, 48), (True, 48), (False, 144)],  # ..
    'S': [(True, 48), (False, 48), (True, 48), (False, 48), (True, 48), (False, 144)],  # ...
    ' ': [(False, 144)],  # Extra word space (total = 3× dit = letter space already there + 144ms)
}

def send_text(text, host='127.0.0.1', jitter_ms=0):
    """
    Send text as CW with optional jitter
    
    Args:
        text: Text to send
        host: Target hostname or IP address
        jitter_ms: Maximum jitter in milliseconds (±jitter_ms)
    """
    protocol = CWProtocol()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print(f"Sending '{text}' to {host}:{UDP_PORT}")
    if jitter_ms > 0:
        print(f"Network jitter: ±{jitter_ms}ms")
    print("=" * 60)
    
    event_count = 0
    for char in text.upper():
        if char not in MORSE_CODE:
            print(f"Skipping unknown character: {char}")
            continue
        
        events = MORSE_CODE[char]
        print(f"\n'{char}' ({len(events)} events):")
        
        for key_down, duration_ms in events:
            # Add random jitter delay
            if jitter_ms > 0:
                jitter = random.uniform(-jitter_ms, jitter_ms) / 1000.0
                time.sleep(max(0, jitter))
            
            packet = protocol.create_packet(key_down, duration_ms)
            sock.sendto(packet, (host, UDP_PORT))
            
            state = "DOWN" if key_down else "UP  "
            event_count += 1
            print(f"  {event_count:2d}. {state} {duration_ms:3d}ms", end='')
            if jitter_ms > 0:
                print(f" (jitter: {jitter*1000:+6.1f}ms)")
            else:
                print()
            
            time.sleep(0.005)  # Small delay between packets
    
    # Send EOT
    eot_packet = protocol.create_eot_packet()
    sock.sendto(eot_packet, (host, UDP_PORT))
    print(f"\n{'=' * 60}")
    print(f"Total events sent: {event_count}")
    print("EOT sent")
    
    sock.close()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Send CW text with optional jitter')
    parser.add_argument('host', nargs='?', default='127.0.0.1', help='Target host IP or hostname (default: 127.0.0.1)')
    parser.add_argument('text', nargs='?', default='PARIS', help='Text to send (default: PARIS)')
    parser.add_argument('--jitter', type=int, default=0, help='Network jitter in ms (default: 0)')
    
    args = parser.parse_args()
    
    send_text(args.text, args.host, args.jitter)
