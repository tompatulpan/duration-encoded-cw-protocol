#!/usr/bin/env python3
"""
Test UDP Timestamp Sender - Using modular protocol structure
"""

import sys
import os
import time
import argparse

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol.udp_ts import CWProtocolUDPTimestamp, UDP_TS_PORT
from audio.sidetone import SidetoneGenerator

# Morse code dictionary
MORSE_CODE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',   'E': '.',
    'F': '..-.',  'G': '--.',   'H': '....',  'I': '..',    'J': '.---',
    'K': '-.-',   'L': '.-..',  'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',  'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',  'Y': '-.--',
    'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '/': '-..-.',  '?': '..--..', '.': '.-.-.-', ',': '--..--',
}

def wpm_to_timing(wpm):
    """Convert WPM to timing values in milliseconds"""
    dit_ms = 1200 // wpm  # PARIS standard
    return {
        'dit': dit_ms,
        'dah': dit_ms * 3,
        'element_space': dit_ms,
        'letter_space': dit_ms * 3,
        'word_space': dit_ms * 7
    }

def send_character(protocol, dest_addr, char, timing, sidetone=None, debug=False):
    """Send a single character"""
    if char == ' ':
        # Word space (additional delay beyond letter space)
        time.sleep(timing['word_space'] / 1000.0)
        return
    
    pattern = MORSE_CODE.get(char.upper())
    if not pattern:
        return  # Skip unknown characters
    
    for i, symbol in enumerate(pattern):
        # Determine duration
        if symbol == '.':
            duration = timing['dit']
        else:  # '-'
            duration = timing['dah']
        
        # Get timestamp before sending
        if protocol.transmission_start is None:
            timestamp_ms = 0
        else:
            timestamp_ms = int((time.time() - protocol.transmission_start) * 1000)
        
        # Send key DOWN event with PREVIOUS state duration (UP/spacing)
        prev_duration = 0 if i == 0 else timing['element_space']
        protocol.send_packet(True, prev_duration, dest_addr)
        if sidetone:
            sidetone.set_key(True)
        
        if debug:
            print(f"[SEND] DOWN {prev_duration}ms (ts={timestamp_ms}ms)")
        
        time.sleep(duration / 1000.0)
        
        # Get timestamp for UP event
        timestamp_ms = int((time.time() - protocol.transmission_start) * 1000)
        
        # Send key UP event with PREVIOUS state duration (element)
        protocol.send_packet(False, duration, dest_addr)
        if sidetone:
            sidetone.set_key(False)
        
        if debug:
            print(f"[SEND] UP {timing['element_space']}ms (ts={timestamp_ms}ms)")
        
        # Wait element space (unless last element)
        if i < len(pattern) - 1:
            time.sleep(timing['element_space'] / 1000.0)
    
    # Letter space (wait after character)
    time.sleep(timing['letter_space'] / 1000.0)

def main():
    parser = argparse.ArgumentParser(description='Test UDP+TS CW Sender (modular)')
    parser.add_argument('host', help='Receiver hostname/IP')
    parser.add_argument('wpm', type=int, help='Words per minute (15-30)')
    parser.add_argument('message', nargs='?', default='CQ CQ TEST', help='Message to send')
    parser.add_argument('--port', type=int, default=UDP_TS_PORT, help=f'UDP port (default: {UDP_TS_PORT})')
    parser.add_argument('--no-sidetone', action='store_true', help='Disable sidetone')
    parser.add_argument('--repeat', type=int, default=1, help='Number of repetitions')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    # Validate WPM
    if not 5 <= args.wpm <= 60:
        print("Error: WPM must be between 5 and 60")
        return 1
    
    # Calculate timing
    timing = wpm_to_timing(args.wpm)
    
    # Create protocol handler
    protocol = CWProtocolUDPTimestamp()
    protocol.create_socket(0)  # Use ephemeral port for sender
    dest_addr = (args.host, args.port)
    
    # Create sidetone (if enabled)
    sidetone = None
    if not args.no_sidetone:
        try:
            sidetone = SidetoneGenerator(frequency=600)  # TX frequency
            print("[AUDIO] Sidetone enabled at 600 Hz")
        except Exception as e:
            print(f"[AUDIO] Warning: Could not initialize audio: {e}")
            print("[AUDIO] Continuing without audio")
    
    print(f"\n[TEST] UDP Timestamp Sender")
    print("[TEST] Using MODULAR protocol structure")
    print(f"[TEST] Target: {args.host}:{args.port}")
    print(f"[TEST] Speed: {args.wpm} WPM")
    print(f"[TEST] Timing: dit={timing['dit']}ms, dah={timing['dah']}ms")
    print(f"[TEST] Message: '{args.message}'")
    print(f"[TEST] Repetitions: {args.repeat}")
    print("-" * 60)
    print()
    
    try:
        for rep in range(args.repeat):
            if args.repeat > 1:
                print(f"\n[REP {rep+1}/{args.repeat}]")
            
            print(f"Sending: {args.message}")
            
            # Send each character
            for char in args.message:
                send_character(protocol, dest_addr, char, timing, sidetone, debug=args.debug)
            
            # Send EOT marker
            print(" [EOT]")
            protocol.send_eot_packet(dest_addr)
            
            # Wait for receiver to drain buffer
            if rep < args.repeat - 1:
                time.sleep(1.0)
    
    except KeyboardInterrupt:
        print("\n\n[TEST] Interrupted by user")
    
    finally:
        # Cleanup
        if sidetone:
            sidetone.close()
        protocol.close()
        
        print(f"\n[TEST] Packets sent: {protocol.sequence_number}")
        print("[TEST] Sender stopped")
    
    return 0

if __name__ == '__main__':
    exit(main())
