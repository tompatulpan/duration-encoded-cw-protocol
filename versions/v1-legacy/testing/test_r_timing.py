#!/usr/bin/env python3
"""
Quick test to send "R" and see timing
"""
import time
import socket
from cw_protocol import CWProtocol, UDP_PORT

# Morse code for "R" = .-. (dit-dah-dit)
# At 25 WPM: dit=48ms, dah=144ms, inter-element space=48ms

protocol = CWProtocol()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

events = [
    (True, 48),   # Dit DOWN (48ms)
    (False, 48),  # Dit UP / space (48ms)
    (True, 144),  # Dah DOWN (144ms)
    (False, 48),  # Dah UP / space (48ms)
    (True, 48),   # Dit DOWN (48ms)
    (False, 144), # Dit UP / end of letter (144ms = 3× dit)
]

print("Sending 'R' (dit-dah-dit) to localhost:7355")
print("=" * 60)

for i, (key_down, duration_ms) in enumerate(events):
    packet = protocol.create_packet(key_down, duration_ms)
    sock.sendto(packet, ('127.0.0.1', UDP_PORT))
    
    state = "DOWN" if key_down else "UP  "
    print(f"Event {i+1}: {state} for {duration_ms:3d}ms")
    
    time.sleep(0.01)  # Small delay between packets

# Send EOT
eot_packet = protocol.create_eot_packet()
sock.sendto(eot_packet, ('127.0.0.1', UDP_PORT))
print("\nEOT sent")
print("=" * 60)

sock.close()
