#!/usr/bin/env python3
"""
Automated CW sender - sends predefined text as CW
No manual key presses required - perfect for testing
"""

import socket
import time
import sys
from cw_protocol import CWProtocol

# Morse code definitions (dit/dah patterns)
MORSE_CODE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',   'E': '.',
    'F': '..-.',  'G': '--.',   'H': '....',  'I': '..',    'J': '.---',
    'K': '-.-',   'L': '.-..',  'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',  'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',  'Y': '-.--',
    'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '/': '-..-.',  '?': '..--..',  ',': '--..--',  '.': '.-.-.-',
    ' ': ' '  # Word space
}

class CWAutoSender:
    def __init__(self, host='localhost', port=7355, wpm=20):
        self.protocol = CWProtocol()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host = host
        self.port = port
        
        # Calculate timing from WPM
        # Standard: PARIS = 50 dits at 20 WPM takes 60 seconds
        # So 1 dit = 1200ms / WPM
        self.dit_ms = int(1200 / wpm)
        self.dah_ms = self.dit_ms * 3
        self.element_space_ms = self.dit_ms  # Space between dits/dahs
        self.char_space_ms = self.dit_ms * 3  # Space between characters
        self.word_space_ms = self.dit_ms * 7  # Space between words
        
        print(f"CW Auto Sender - {wpm} WPM")
        print(f"Timings: dit={self.dit_ms}ms, dah={self.dah_ms}ms")
        print(f"Sending to {host}:{port}")
        print("-" * 50)
    
    def send_event(self, key_down, duration_ms):
        """Send a single CW event"""
        packet = self.protocol.create_packet(
            key_down=key_down,
            duration_ms=duration_ms
        )
        self.sock.sendto(packet, (self.host, self.port))
        
        # Display progress
        if key_down:
            symbol = '▬' if duration_ms > self.dit_ms * 2 else '▪'
            print(symbol, end='', flush=True)
    
    def send_element(self, is_dah):
        """Send a single dit or dah"""
        duration = self.dah_ms if is_dah else self.dit_ms
        
        # Key down
        self.send_event(True, duration)
        time.sleep(duration / 1000.0)
        
        # Small delay to prevent UDP buffer overflow
        time.sleep(0.001)  # 1ms safety margin
        
        # Key up (element space)
        self.send_event(False, self.element_space_ms)
        time.sleep(self.element_space_ms / 1000.0)
    
    def send_character(self, char):
        """Send a single character in morse code"""
        char = char.upper()
        
        if char == ' ':
            # Word space (already had char space, add remaining)
            extra_space = self.word_space_ms - self.char_space_ms
            time.sleep(extra_space / 1000.0)
            print('  ', end='', flush=True)
            return
        
        if char not in MORSE_CODE:
            print(f'?', end='', flush=True)
            return
        
        pattern = MORSE_CODE[char]
        
        for element in pattern:
            if element == '.':
                self.send_element(False)  # Dit
            elif element == '-':
                self.send_element(True)   # Dah
        
        # Character space (subtract element space we just did)
        char_space = self.char_space_ms - self.element_space_ms
        time.sleep(char_space / 1000.0)
        print(' ', end='', flush=True)
    
    def send_text(self, text):
        """Send entire text message"""
        print(f"\nSending: {text}")
        print("Pattern: ", end='', flush=True)
        
        start_time = time.time()
        
        for char in text:
            self.send_character(char)
        
        elapsed = time.time() - start_time
        print(f"\n\nSent in {elapsed:.1f}s")
        
        # Calculate actual WPM (using PARIS standard)
        # Each character has a standard weight
        char_count = len(text.replace(' ', ''))
        actual_wpm = (char_count * 60) / (elapsed * 5)  # PARIS = 5 chars
        print(f"Effective speed: {actual_wpm:.1f} WPM")
    
    def close(self):
        self.sock.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 cw_auto_sender.py <host> [wpm] [text]")
        print("\nExamples:")
        print("  python3 cw_auto_sender.py localhost")
        print("  python3 cw_auto_sender.py localhost 25")
        print("  python3 cw_auto_sender.py localhost 20 'CQ CQ DE N0CALL'")
        print("\nDefault tests:")
        print("  1. PARIS (standard timing word)")
        print("  2. CQ CQ CQ DE TEST")
        print("  3. Quick brown fox")
        return 1
    
    host = sys.argv[1]
    wpm = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    
    sender = CWAutoSender(host=host, port=7355, wpm=wpm)
    
    try:
        if len(sys.argv) > 3:
            # User provided text
            text = ' '.join(sys.argv[3:])
            sender.send_text(text)
        else:
            # Run default test sequence
            tests = [
                "PARIS",
                "CQ CQ CQ DE TEST",
                "THE QUICK BROWN FOX",
                "73"
            ]
            
            for i, text in enumerate(tests, 1):
                print(f"\n{'='*50}")
                print(f"Test {i}/{len(tests)}")
                sender.send_text(text)
                
                if i < len(tests):
                    print("\nWaiting 2 seconds before next test...")
                    time.sleep(2)
        
        print("\n" + "="*50)
        print("✓ Transmission complete!")
        
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
    finally:
        sender.close()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
