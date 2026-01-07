#!/usr/bin/env python3
"""
Interactive CW sender - type text in real-time with queue/buffer system
Characters are queued and sent as you type, like a real CW keyboard
"""

import socket
import time
import sys
import threading
import queue
from cw_protocol import CWProtocol

# Morse code definitions
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
    '=': '-...-',  '+': '.-.-.',   '@': '.--.-.',
    ' ': ' '  # Word space
}

class CWInteractiveSender:
    def __init__(self, host='localhost', port=7355, wpm=20):
        self.protocol = CWProtocol()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host = host
        self.port = port
        
        # Character queue (thread-safe)
        self.char_queue = queue.Queue()
        self.running = True
        
        # Calculate timing from WPM
        self.dit_ms = int(1200 / wpm)
        self.dah_ms = self.dit_ms * 3
        self.element_space_ms = self.dit_ms
        self.char_space_ms = self.dit_ms * 3
        self.word_space_ms = self.dit_ms * 7
        self.wpm = wpm
        
        print("=" * 60)
        print(f"CW Interactive Sender - {wpm} WPM")
        print(f"Sending to {host}:{port}")
        print("=" * 60)
        print("\n💡 TIP: If connecting over internet fails:")
        print("   - Check router UDP port forwarding (7355)")
        print("   - Check firewall: sudo ufw allow 7355/udp")
        print("   - NAT hairpinning: test from OUTSIDE your network")
        print("\nType your message and press ENTER to send each line.")
        print("Characters are queued and sent in real-time.")
        print("Press Ctrl+C to quit.")
        print("\nQueue status shown as: [buffer: X chars] > text...")
        print("-" * 60)
        print("\nReady! Type your first message:")
        print("> ", end='', flush=True)
    
    def send_event(self, key_down, duration_ms):
        """Send a single CW event"""
        packet = self.protocol.create_packet(
            key_down=key_down,
            duration_ms=duration_ms
        )
        self.sock.sendto(packet, (self.host, self.port))
    
    def send_element(self, is_dah, is_last_in_char=False):
        """Send a single dit or dah
        
        Args:
            is_dah: True for dah, False for dit
            is_last_in_char: True if this is the last element in the character
        """
        duration = self.dah_ms if is_dah else self.dit_ms
        
        # Send key down event
        send_time = time.time()
        self.send_event(True, duration)
        
        # Wait for the duration (simulate real-time keying)
        elapsed = (time.time() - send_time) * 1000
        remaining = duration - elapsed
        if remaining > 0:
            time.sleep(remaining / 1000.0)
        
        # Send key up event - use char_space for last element, element_space otherwise
        up_duration = self.char_space_ms if is_last_in_char else self.element_space_ms
        send_time = time.time()
        self.send_event(False, up_duration)
        
        # Wait for the up duration
        elapsed = (time.time() - send_time) * 1000
        remaining = up_duration - elapsed
        if remaining > 0:
            time.sleep(remaining / 1000.0)
    
    def send_character(self, char):
        """Send a single character in morse code"""
        char = char.upper()
        
        if char == ' ':
            # Word space - just sleep the extra time beyond char_space
            # The previous character already sent char_space in its last UP packet
            # We only need to add the difference to make it a full word_space
            extra_space = self.word_space_ms - self.char_space_ms
            time.sleep(extra_space / 1000.0)
            return True
        
        if char not in MORSE_CODE:
            return False  # Unknown character
        
        pattern = MORSE_CODE[char]
        
        for i, element in enumerate(pattern):
            is_last = (i == len(pattern) - 1)
            if element == '.':
                self.send_element(False, is_last_in_char=is_last)  # Dit
            elif element == '-':
                self.send_element(True, is_last_in_char=is_last)   # Dah
        
        # Character space is now sent by send_element() for the last element
        # No need for additional sleep here
        
        return True
    
    def sender_thread(self):
        """Background thread that sends queued characters"""
        while self.running:
            try:
                # Get next character (block with timeout)
                char = self.char_queue.get(timeout=0.1)
                
                # Send it (no visual feedback here - done in input thread)
                self.send_character(char)
                self.char_queue.task_done()
                
            except queue.Empty:
                continue
    
    def input_thread(self):
        """Foreground thread that reads user input"""
        while self.running:
            try:
                # Read line from user (input() already echoes the text)
                line = input()
                
                if not line:
                    print("> ", end='', flush=True)
                    continue
                
                # Show what we're sending
                print(f"[Sending: {line}]", flush=True)
                
                # Queue each character
                for char in line:
                    self.char_queue.put(char)
                
                # Add space after each line
                self.char_queue.put(' ')
                
                # Wait for queue to drain
                self.char_queue.join()
                
                # Send EOT (End-of-Transmission) marker
                eot_packet = self.protocol.create_eot_packet()
                self.sock.sendto(eot_packet, (self.host, self.port))
                
                print("[Done]")  # Signal completion
                print("> ", end='', flush=True)  # Prompt for next line
                
            except EOFError:
                # End of input (Ctrl+D)
                break
            except KeyboardInterrupt:
                break
    
    def run(self):
        """Run the interactive sender"""
        try:
            # Start sender thread
            sender = threading.Thread(target=self.sender_thread, daemon=True)
            sender.start()
            
            # Run input in main thread
            self.input_thread()
            
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        finally:
            self.running = False
            self.sock.close()
            print("73!")


class CWBufferedSender(CWInteractiveSender):
    """
    Buffered sender - type ahead while transmitting
    Shows real-time buffer status
    """
    
    def __init__(self, host='localhost', port=7355, wpm=20, max_buffer=100):
        super().__init__(host, port, wpm)
        self.max_buffer = max_buffer
        print(f"\nBuffer size: {max_buffer} characters")
        print("Type ahead while transmitting - your text will be queued!")
        print("Each character is sent as you type (no ENTER needed)")
        print("-" * 60)
        print("\nStart typing (Ctrl+C to quit):")
        print()
    
    def input_thread(self):
        """Enhanced input thread with continuous character-by-character input"""
        try:
            import sys
            import select
            import tty
            import termios
            
            # Save terminal settings
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            
            last_queue_size = 0
            
            try:
                while self.running:
                    # Show queue status if changed
                    queue_size = self.char_queue.qsize()
                    if queue_size != last_queue_size:
                        if queue_size > 0:
                            print(f'\r[Queue: {queue_size:3d}] ', end='', flush=True)
                        else:
                            print(f'\r              \r', end='', flush=True)
                        last_queue_size = queue_size
                    
                    # Check for input (non-blocking)
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        char = sys.stdin.read(1)
                        
                        if char == '\x03':  # Ctrl+C
                            break
                        elif char == '\x04':  # Ctrl+D
                            break
                        elif char == '\n' or char == '\r':
                            # Space for word separation
                            if self.char_queue.qsize() < self.max_buffer:
                                self.char_queue.put(' ')
                                print(' ', end='', flush=True)
                            else:
                                print("\n[BUFFER FULL!]\n", flush=True)
                        elif char == '\x7f' or char == '\x08':  # Backspace
                            # Can't undo queued characters, just visual feedback
                            print('\b \b', end='', flush=True)
                        else:
                            # Queue character immediately
                            if self.char_queue.qsize() < self.max_buffer:
                                self.char_queue.put(char)
                                # Echo character
                                print(char, end='', flush=True)
                            else:
                                print("\n[BUFFER FULL!]\n", flush=True)
            
            finally:
                # Restore terminal
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                
        except ImportError:
            # Fall back to line-based input if termios not available
            print("\n[Character-by-character input not available, using line mode]")
            super().input_thread()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 cw_interactive_sender.py <host> [wpm] [--buffered]")
        print("\nExamples:")
        print("  python3 cw_interactive_sender.py localhost")
        print("  python3 cw_interactive_sender.py localhost 25")
        print("  python3 cw_interactive_sender.py 192.168.1.100 20 --buffered")
        return 1
    
    host = sys.argv[1]
    wpm = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    buffered = '--buffered' in sys.argv or '-b' in sys.argv
    
    if buffered:
        sender = CWBufferedSender(host=host, port=7355, wpm=wpm)
    else:
        sender = CWInteractiveSender(host=host, port=7355, wpm=wpm)
    
    sender.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
