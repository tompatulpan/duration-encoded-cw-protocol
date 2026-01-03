#!/usr/bin/env python3
"""
Test UDP Sender - Using modular protocol structure
"""

import sys
import os
import time
import argparse

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol.udp import CWProtocolUDP
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

def send_character(protocol, char, timing, sidetone=None):
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
        
        # Send key DOWN event with PREVIOUS state duration (UP/spacing)
        prev_duration = 0 if i == 0 else timing['element_space']
        protocol.send_packet(True, prev_duration)
        if sidetone:
            sidetone.set_key(True)
        time.sleep(duration / 1000.0)
        
        # Send key UP event with PREVIOUS state duration (element)
        protocol.send_packet(False, duration)
        if sidetone:
            sidetone.set_key(False)
        
        # Wait element space (unless last element)
        if i < len(pattern) - 1:
            time.sleep(timing['element_space'] / 1000.0)
    
    # Letter space (wait after character)
    time.sleep(timing['letter_space'] / 1000.0)

def main():
    parser = argparse.ArgumentParser(description='Test UDP CW Sender (modular)')
    parser.add_argument('host', help='Receiver hostname/IP')
    parser.add_argument('wpm', type=int, help='Words per minute (15-30)')
    parser.add_argument('message', nargs='?', default='CQ CQ TEST', help='Message to send')
    parser.add_argument('--port', type=int, default=7355, help='UDP port (default: 7355)')
    parser.add_argument('--no-sidetone', action='store_true', help='Disable sidetone')
    parser.add_argument('--repeat', type=int, default=1, help='Number of repetitions')
    args = parser.parse_args()
    
    # Validate WPM
    if not 5 <= args.wpm <= 60:
        print("Error: WPM must be between 5 and 60")
        return 1
    
    # Calculate timing
    timing = wpm_to_timing(args.wpm)
    
    # Create protocol handler
    protocol = CWProtocolUDP(host=args.host, port=args.port)
    protocol.connect()
    
    # Create sidetone (if enabled)
    sidetone = None
    if not args.no_sidetone:
        try:
            sidetone = SidetoneGenerator(frequency=600)  # 600 Hz for TX
            print("[AUDIO] Sidetone enabled at 600 Hz")
        except Exception as e:
            print(f"[AUDIO] Warning: Could not initialize audio: {e}")
            print("[AUDIO] Continuing without sidetone")
    
    print(f"\n[TEST] UDP Sender")
    print("[TEST] Using MODULAR protocol structure")
    print(f"[TEST] Target: {args.host}:{args.port}")
    print(f"[TEST] Speed: {args.wpm} WPM")
    print(f"[TEST] Timing: dit={timing['dit']}ms, dah={timing['dah']}ms")
    print(f"[TEST] Message: '{args.message}'")
    print(f"[TEST] Repetitions: {args.repeat}")
    print("-" * 60)
    
    try:
        for rep in range(args.repeat):
            if args.repeat > 1:
                print(f"\n[{rep+1}/{args.repeat}] Sending: {args.message}")
            else:
                print(f"\nSending: {args.message}")
            
            # Send message
            for char in args.message:
                print(char, end='', flush=True)
                send_character(protocol, char, timing, sidetone)
            
            # Send EOT
            protocol.send_eot()
            print(" [EOT]")
            
            # Wait between repetitions
            if rep < args.repeat - 1:
                time.sleep(2.0)
    
    except KeyboardInterrupt:
        print("\n\n[TEST] Interrupted")
    
    finally:
        # Cleanup
        if sidetone:
            sidetone.close()
        protocol.close()
        print("[TEST] Sender stopped")
    
    return 0

if __name__ == '__main__':
    exit(main())
