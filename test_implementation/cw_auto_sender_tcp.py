#!/usr/bin/env python3
"""
CW Automated Sender TCP - Send text as CW over TCP
Usage: cw_auto_sender_tcp.py <host> <wpm> <text>
"""

import sys
import time
import argparse
from cw_protocol_tcp import CWProtocolTCP, TCP_PORT

# Audio support (optional)
try:
    from cw_receiver import SidetoneGenerator
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: Audio sidetone not available (cw_receiver.py import failed)")


def send_text_tcp(text, host='127.0.0.1', port=TCP_PORT, wpm=25, enable_audio=True):
    """
    Send text as CW over TCP
    
    Args:
        text: Text to send
        host: Target host
        port: TCP port
        wpm: Words per minute (12-35)
    """
    protocol = CWProtocolTCP()
    
    # Initialize sidetone generator
    sidetone = None
    if enable_audio and AUDIO_AVAILABLE:
        try:
            sidetone = SidetoneGenerator(frequency=600)  # 600 Hz for TX
            print("[AUDIO] Sidetone enabled (600 Hz)")
        except Exception as e:
            print(f"[AUDIO] Failed to initialize sidetone: {e}")
            sidetone = None
    
    # Connect to receiver
    print(f"[TCP] Connecting to {host}:{port}...")
    if not protocol.connect(host, port, timeout=10.0):
        print(f"[TCP] Failed to connect to {host}:{port}")
        return False
    
    print(f"[TCP] Connected successfully")
    
    # Calculate timing
    dit_ms = int(1200 / wpm)
    dah_ms = dit_ms * 3
    
    print(f"Sending '{text}' to {host}:{port} at {wpm} WPM")
    print(f"Timing: dit={dit_ms}ms, dah={dah_ms}ms")
    print("=" * 60)
    
    # Morse code table
    morse_table = {
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
    
    packet_count = 0
    last_key_state = None  # Track last state to avoid redundant packets
    
    try:
        for char in text.upper():
            if char not in morse_table:
                print(f"  [SKIP] Unknown character: '{char}'")
                continue
            
            if char == ' ':
                # Word space: just wait (we're already in UP state from previous letter)
                # Total word space is 7 dits, but we already sent 3 dits after last letter
                # So wait additional 4 dits
                word_space_duration = dit_ms * 4
                print("  [SPACE]")
                # Sidetone is already off from previous letter space
                time.sleep(word_space_duration / 1000.0)
                continue
            
            morse = morse_table[char]
            print(f"{char} ({morse}):", end=' ', flush=True)
            
            for i, symbol in enumerate(morse):
                # Key down
                duration = dah_ms if symbol == '-' else dit_ms
                if not protocol.send_packet(True, duration):
                    print("\n[TCP] Send failed - connection lost")
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
                    space_duration = dit_ms
                    if not protocol.send_packet(False, space_duration):
                        print("\n[TCP] Send failed - connection lost")
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
                    space_duration = dit_ms * 3
                    if not protocol.send_packet(False, space_duration):
                        print("\n[TCP] Send failed - connection lost")
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
        print("=" * 60)
        print(f"Total packets sent: {packet_count}")
        print("[TCP] Sending End-of-Transmission...")
        
        if not protocol.send_eot_packet():
            print("[TCP] Failed to send EOT")
        else:
            print("[TCP] EOT sent successfully")
        
        # Wait for receiver to drain buffer completely
        # This prevents overlapping transmissions and audio desync
        print("[TCP] Waiting for buffer to drain...")
        time.sleep(1.0)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    finally:
        # Cleanup
        if sidetone:
            sidetone.close()
        protocol.close()
        print("[TCP] Connection closed")
    
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='CW Automated Sender - TCP Version',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s localhost 25 "CQ CQ DE CALLSIGN"
  %(prog)s 192.168.1.100 20 "TEST TEST"
  %(prog)s remote.example.com 30 "73 ES CUL"
        '''
    )
    parser.add_argument('host', help='Target host (IP address or hostname)')
    parser.add_argument('wpm', type=int, help='Words per minute (12-35 recommended)')
    parser.add_argument('text', help='Text to send as CW')
    parser.add_argument('--port', type=int, default=TCP_PORT, 
                       help=f'TCP port (default: {TCP_PORT})')
    parser.add_argument('--no-audio', action='store_true', 
                       help='Disable sidetone audio on sender')
    
    args = parser.parse_args()
    
    # Validate WPM
    if args.wpm < 5 or args.wpm > 60:
        print(f"Warning: WPM {args.wpm} is outside normal range (5-60)")
        print("Continuing anyway...")
    
    print("=" * 60)
    print("CW Automated Sender - TCP Version")
    print("=" * 60)
    print()
    
    success = send_text_tcp(args.text, args.host, args.port, args.wpm, 
                            enable_audio=not args.no_audio)
    
    if not success:
        sys.exit(1)
