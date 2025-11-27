#!/usr/bin/env python3
"""
Test script to verify keyer output without hardware
Simulates paddle inputs and shows what packets would be sent
"""

import sys
import time

# Add parent directory to path
sys.path.insert(0, '.')

from cw_usb_key_sender import IambicKeyer

def test_keyer():
    """Test the keyer logic with simulated inputs"""
    keyer = IambicKeyer(wpm=25, mode='B')
    
    sent_packets = []
    
    def record_event(key_down, duration_ms):
        """Record what would be sent"""
        sent_packets.append((key_down, duration_ms))
        state_str = "DOWN" if key_down else "UP  "
        print(f"  Send: {state_str} {duration_ms:3.0f}ms")
    
    print("Testing IambicKeyer at 25 WPM (dit=48ms)")
    print("=" * 60)
    
    # Test 1: Single dit (E)
    print("\nTest 1: Single dit paddle press (letter E)")
    print("-" * 60)
    keyer.state = keyer.IDLE
    active = keyer.update(dit_paddle=True, dah_paddle=False, send_element_callback=record_event)
    active = keyer.update(dit_paddle=False, dah_paddle=False, send_element_callback=record_event)
    print(f"Packets sent: {len(sent_packets)}")
    print(f"Active after release: {active}")
    
    # Check for duplicates
    for i in range(1, len(sent_packets)):
        prev_state, prev_dur = sent_packets[i-1]
        curr_state, curr_dur = sent_packets[i]
        if prev_state == curr_state:
            print(f"⚠️  DUPLICATE STATE: {i-1} and {i} both {'DOWN' if curr_state else 'UP'}")
    
    sent_packets.clear()
    
    # Test 2: Dit-dit-dit-dah (V)
    print("\nTest 2: V (dit-dit-dit-dah)")
    print("-" * 60)
    keyer.state = keyer.IDLE
    
    # Dit 1
    keyer.update(dit_paddle=True, dah_paddle=False, send_element_callback=record_event)
    # Dit 2
    keyer.update(dit_paddle=True, dah_paddle=False, send_element_callback=record_event)
    # Dit 3
    keyer.update(dit_paddle=True, dah_paddle=False, send_element_callback=record_event)
    # Dah
    keyer.update(dit_paddle=False, dah_paddle=True, send_element_callback=record_event)
    # Release
    keyer.update(dit_paddle=False, dah_paddle=False, send_element_callback=record_event)
    
    print(f"Packets sent: {len(sent_packets)}")
    
    # Check for duplicates
    for i in range(1, len(sent_packets)):
        prev_state, prev_dur = sent_packets[i-1]
        curr_state, curr_dur = sent_packets[i]
        if prev_state == curr_state:
            print(f"⚠️  DUPLICATE STATE: packets {i-1} and {i} both {'DOWN' if curr_state else 'UP'}")
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"Total packets: {len(sent_packets)}")
    print("State alternation:", "✓ CORRECT" if all(
        sent_packets[i][0] != sent_packets[i+1][0] for i in range(len(sent_packets)-1)
    ) else "✗ ERROR - duplicates found")

if __name__ == '__main__':
    test_keyer()
