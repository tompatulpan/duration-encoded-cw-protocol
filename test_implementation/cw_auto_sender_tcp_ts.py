#!/usr/bin/env python3
"""
CW Automated Sender TCP with Timestamps
Send text as CW over TCP with relative timestamps for realtime sync
"""

import sys
import time
import argparse
from cw_protocol_tcp_ts import CWProtocolTCPTimestamp, TCP_PORT

# Audio support (optional)
try:
    from cw_receiver import SidetoneGenerator
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


# Morse code table
MORSE_TABLE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '/': '-..-.', '?': '..--..', '.': '.-.-.-', ',': '--..--',
    ' ': ' '
}


def send_text_tcp_ts(text, host='127.0.0.1', port=TCP_PORT, wpm=25, enable_audio=True):
    """Send text as CW over TCP with timestamps"""
    
    protocol = CWProtocolTCPTimestamp()
    
    # Initialize sidetone
    sidetone = None
    if enable_audio and AUDIO_AVAILABLE:
        try:
            sidetone = SidetoneGenerator(frequency=600)
            print("[AUDIO] Sidetone enabled (600 Hz)")
        except Exception as e:
            print(f"[AUDIO] Failed: {e}")
    
    # Connect
    print(f"[TCP-TS] Connecting to {host}:{port}...")
    if not protocol.connect(host, port, timeout=10.0):
        print(f"[TCP-TS] Connection failed")
        return False
    
    print(f"[TCP-TS] Connected successfully")
    
    # Calculate timing
    dit_ms = int(1200 / wpm)
    dah_ms = dit_ms * 3
    element_space_ms = dit_ms
    char_space_ms = dit_ms * 3
    word_space_ms = dit_ms * 7
    
    print(f"\nSending: '{text}' at {wpm} WPM (with timestamps)")
    print(f"Timing: dit={dit_ms}ms, dah={dah_ms}ms")
    print("=" * 60)
    
    packet_count = 0
    
    try:
        for char in text.upper():
            if char not in MORSE_TABLE:
                continue
            
            morse = MORSE_TABLE[char]
            
            if char == ' ':
                # Word space - just sleep extra time
                time.sleep((word_space_ms - char_space_ms) / 1000.0)
                print('  ', end='', flush=True)
                continue
            
            # Send morse pattern for character
            for i, symbol in enumerate(morse):
                # Key down
                duration = dah_ms if symbol == '-' else dit_ms
                if not protocol.send_packet(True, duration):
                    print("\n[TCP-TS] Send failed - connection lost")
                    if sidetone:
                        sidetone.set_key(False)
                    return False
                packet_count += 1
                print(f"[TX {packet_count}]", end='', flush=True)
                
                # Turn on sidetone
                if sidetone:
                    sidetone.set_key(True)
                
                print(symbol, end='', flush=True)
                
                # Wait for key-down duration (actual CW timing)
                time.sleep(duration / 1000.0)
                
                # Key up (inter-element or letter space)
                if i < len(morse) - 1:
                    # Inter-element space (1 dit unit)
                    space_duration = element_space_ms
                    if not protocol.send_packet(False, space_duration):
                        print("\n[TCP-TS] Send failed - connection lost")
                        if sidetone:
                            sidetone.set_key(False)
                        return False
                    packet_count += 1
                    
                    # Turn off sidetone
                    if sidetone:
                        sidetone.set_key(False)
                    
                    # Wait for inter-element space
                    time.sleep(space_duration / 1000.0)
                else:
                    # Letter space (3 dit units)
                    space_duration = char_space_ms
                    if not protocol.send_packet(False, space_duration):
                        print("\n[TCP-TS] Send failed - connection lost")
                        if sidetone:
                            sidetone.set_key(False)
                        return False
                    packet_count += 1
                    
                    # Turn off sidetone
                    if sidetone:
                        sidetone.set_key(False)
                    
                    # Wait for letter space
                    time.sleep(space_duration / 1000.0)
            
            print()  # Newline after character
        
        # Send EOT
        protocol.send_eot_packet()
        print(f"\n[TCP-TS] Sent {packet_count} packets")
        
        # Give receiver time to drain buffer
        time.sleep(1.0)
        
    finally:
        if sidetone:
            sidetone.close()
        protocol.close()
    
    return True


def main():
    parser = argparse.ArgumentParser(description='CW Automated Sender TCP with Timestamps')
    parser.add_argument('host', help='Receiver hostname or IP')
    parser.add_argument('wpm', type=int, default=25, nargs='?', help='Words per minute (12-35)')
    parser.add_argument('text', nargs='?', default='5 CQ CQ CQ', help='Text to send')
    parser.add_argument('--no-audio', action='store_true', help='Disable audio sidetone')
    
    args = parser.parse_args()
    
    # Validate WPM
    if not 12 <= args.wpm <= 35:
        print("Error: WPM must be between 12 and 35")
        return 1
    
    # Send text
    success = send_text_tcp_ts(
        args.text,
        host=args.host,
        wpm=args.wpm,
        enable_audio=not args.no_audio
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
