#!/bin/bash
# Automated loopback test for CW protocol

echo "==================================="
echo "CW Protocol Loopback Test"
echo "==================================="
echo

# Test protocol encoding/decoding
echo "1. Testing protocol encoding/decoding..."
python3 cw_protocol.py
echo

# Check if pyaudio is available
if python3 -c "import pyaudio" 2>/dev/null; then
    echo "✓ PyAudio available - audio sidetone will work"
else
    echo "✗ PyAudio not available - install with: pip3 install pyaudio"
fi
echo

echo "2. Manual test:"
echo "   Open two terminals:"
echo "   Terminal 1: python3 cw_receiver.py"
echo "   Terminal 2: python3 cw_sender.py localhost"
echo
echo "   Press SPACE in sender to toggle key state"
echo "   Press Q to quit"
echo

# Create a simple automated test
echo "3. Running automated timing test..."
python3 << 'EOF'
import time
from cw_protocol import CWProtocol

protocol = CWProtocol()

print("\nSimulating 'PARIS' at 20 WPM:")
print("(60ms dit, 180ms dah, 60ms space, 180ms letter space, 420ms word space)")
print()

# P = .--. 
pattern = [
    ('P', [
        (True, 60),   # dit
        (False, 60),  # space
        (True, 180),  # dah
        (False, 60),  # space
        (True, 180),  # dah
        (False, 60),  # space
        (True, 60),   # dit
        (False, 180), # letter space
    ]),
    ('A', [
        (True, 60),   # dit
        (False, 60),  # space
        (True, 180),  # dah
        (False, 180), # letter space
    ]),
    ('R', [
        (True, 60),   # dit
        (False, 60),  # space
        (True, 180),  # dah
        (False, 60),  # space
        (True, 60),   # dit
        (False, 180), # letter space
    ]),
    ('I', [
        (True, 60),   # dit
        (False, 60),  # space
        (True, 60),   # dit
        (False, 180), # letter space
    ]),
    ('S', [
        (True, 60),   # dit
        (False, 60),  # space
        (True, 60),   # dit
        (False, 60),  # space
        (True, 60),   # dit
        (False, 420), # word space
    ]),
]

total_time = 0
total_bytes = 0

for char, events in pattern:
    print(f"Character '{char}':")
    for key_down, duration in events:
        packet = protocol.create_packet(key_down, duration)
        total_bytes += len(packet)
        total_time += duration
        
        state = "DOWN" if key_down else "UP  "
        print(f"  {state} {duration:3d}ms -> packet: {packet.hex()}")
    print()

print(f"Total time for 'PARIS': {total_time}ms = {total_time/1000:.2f}s")
print(f"Total bytes transmitted: {total_bytes} bytes")
print(f"Bandwidth used: {total_bytes * 8 / (total_time/1000):.1f} bps")
print(f"Expected for PARIS at 20 WPM: ~2.4s (2400ms)")
print(f"Actual/Expected ratio: {(total_time/2400)*100:.1f}%")

EOF

echo
echo "==================================="
echo "Test complete!"
echo "==================================="
