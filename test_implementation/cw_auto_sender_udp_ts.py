#!/usr/bin/env python3
"""
CW Auto Sender UDP with Timestamps
Automatically sends CW text over UDP with timestamps at specified WPM
"""

import argparse
import time
from cw_protocol_udp_ts import CWProtocolUDPTimestamp, UDP_TS_PORT
from cw_receiver import SidetoneGenerator

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
    '.': '.-.-.-', ',': '--..--', '?': '..--..', '/': '-..-.',
    '=': '-...-', '+': '.-.-.', '-': '-....-', '@': '.--.-.',
}


class CWAutoSenderUDPTimestamp:
    """Automatic CW sender for UDP timestamp protocol"""
    
    def __init__(self, host, port, wpm, sidetone_enabled=True, debug=False):
        self.host = host
        self.port = port
        self.wpm = wpm
        self.sidetone_enabled = sidetone_enabled
        self.debug = debug
        
        # Calculate timing (all in milliseconds)
        self.dit_ms = int(1200 / wpm)
        self.dah_ms = self.dit_ms * 3
        self.element_space_ms = self.dit_ms
        self.letter_space_ms = self.dit_ms * 3
        self.word_space_ms = self.dit_ms * 7
        
        # Protocol
        self.protocol = CWProtocolUDPTimestamp()
        self.dest_addr = (host, port)
        
        # Sidetone (TX frequency)
        self.sidetone = None
        if sidetone_enabled:
            self.sidetone = SidetoneGenerator(frequency=600)
        
        print(f"CW Auto Sender UDP Timestamp: {host}:{port}")
        print(f"Speed: {wpm} WPM")
        print(f"Timing - Dit: {self.dit_ms}ms, Dah: {self.dah_ms}ms")
        print(f"Spaces - Element: {self.element_space_ms}ms, Letter: {self.letter_space_ms}ms, Word: {self.word_space_ms}ms")
    
    def send_event(self, key_down, duration_ms):
        """Send CW event with real-time timing"""
        # Get current timestamp before sending
        if self.protocol.transmission_start is None:
            timestamp_ms = 0
        else:
            timestamp_ms = int((time.time() - self.protocol.transmission_start) * 1000)
        
        # Send packet
        self.protocol.send_packet(key_down, duration_ms, self.dest_addr)
        
        # Control sidetone
        if self.sidetone:
            self.sidetone.set_key(key_down)
        
        # Wait for the duration (real-time transmission)
        time.sleep(duration_ms / 1000.0)
        
        if self.debug:
            state_str = "DOWN" if key_down else "UP"
            print(f"[SEND] {state_str} {duration_ms}ms (ts={timestamp_ms}ms)")
    
    def send_dit(self):
        """Send dit"""
        self.send_event(True, self.dit_ms)
        self.send_event(False, self.element_space_ms)
    
    def send_dah(self):
        """Send dah"""
        self.send_event(True, self.dah_ms)
        self.send_event(False, self.element_space_ms)
    
    def send_character(self, char):
        """Send single character"""
        char = char.upper()
        
        if char == ' ':
            # Word space (already have element space from previous character)
            additional_space = self.word_space_ms - self.element_space_ms
            time.sleep(additional_space / 1000.0)
            return
        
        if char not in MORSE_CODE:
            print(f"[WARNING] Character '{char}' not in Morse code dictionary")
            return
        
        pattern = MORSE_CODE[char]
        
        if self.debug:
            print(f"[CHAR] '{char}' = {pattern}")
        
        for element in pattern:
            if element == '.':
                self.send_dit()
            elif element == '-':
                self.send_dah()
        
        # Letter space (replace last element space with letter space)
        additional_space = self.letter_space_ms - self.element_space_ms
        time.sleep(additional_space / 1000.0)
    
    def send_text(self, text):
        """Send text message"""
        print(f"\nSending: '{text}'")
        print("="*50)
        
        # Create socket
        self.protocol.sock = self.protocol.create_socket(0)  # Use ephemeral port
        
        for char in text:
            self.send_character(char)
        
        # Send End-of-Transmission marker
        print("\n[EOT] Sending end-of-transmission marker")
        self.protocol.send_eot_packet(self.dest_addr)
        
        # Wait for receiver to drain buffer
        time.sleep(1.0)
        
        print("\nTransmission complete.")
        print(f"Packets sent: {self.protocol.sequence_number}")


def main():
    parser = argparse.ArgumentParser(description='CW Auto Sender UDP with Timestamps')
    parser.add_argument('host', help='Receiver hostname or IP address')
    parser.add_argument('wpm', type=int, help='Words per minute (15-30 typical)')
    parser.add_argument('text', help='Text to send in Morse code')
    parser.add_argument('--port', type=int, default=UDP_TS_PORT,
                       help=f'UDP port (default: {UDP_TS_PORT})')
    parser.add_argument('--no-sidetone', action='store_true',
                       help='Disable sidetone audio')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug output')
    
    args = parser.parse_args()
    
    sender = CWAutoSenderUDPTimestamp(
        host=args.host,
        port=args.port,
        wpm=args.wpm,
        sidetone_enabled=not args.no_sidetone,
        debug=args.debug
    )
    
    try:
        sender.send_text(args.text)
    finally:
        if sender.sidetone:
            sender.sidetone.close()
        if sender.protocol.sock:
            sender.protocol.close()


if __name__ == '__main__':
    main()
