#!/usr/bin/env python3
"""
CW Automated Sender TCP with Timestamps
Send text as CW over TCP with relative timestamps for realtime sync
"""

import sys
import time
import argparse
import configparser
import os
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


def send_text_tcp_ts(text, host='127.0.0.1', port=TCP_PORT, wpm=25, enable_audio=True, debug=False):
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
    previous_spacing_ms = 0  # Track spacing before current element
    
    try:
        for char_idx, char in enumerate(text.upper()):
            if char not in MORSE_TABLE:
                continue
            
            morse = MORSE_TABLE[char]
            
            if char == ' ':
                # Word space - just sleep extra time beyond letter space
                time.sleep((word_space_ms - char_space_ms) / 1000.0)
                previous_spacing_ms = word_space_ms  # Update for next character
                print('  ', end='', flush=True)
                continue
            
            # Send morse pattern for character
            for i, symbol in enumerate(morse):
                # Determine element duration
                element_duration = dah_ms if symbol == '-' else dit_ms
                
                # CORRECTED PROTOCOL: Send key DOWN with PREVIOUS spacing duration
                if not protocol.send_packet(True, previous_spacing_ms):
                    print("\n[TCP-TS] Send failed - connection lost")
                    if sidetone:
                        sidetone.set_key(False)
                    return False
                packet_count += 1
                
                if debug:
                    timestamp_ms = int((time.time() - protocol.transmission_start) * 1000) if protocol.transmission_start else 0
                    print(f"[SEND] DOWN (previous spacing: {previous_spacing_ms}ms, ts={timestamp_ms}ms)")
                else:
                    print(f"[TX {packet_count}]", end='', flush=True)
                
                # Turn on sidetone
                if sidetone:
                    sidetone.set_key(True)
                
                print(symbol, end='', flush=True)
                
                # Wait for element duration (actual CW timing)
                time.sleep(element_duration / 1000.0)
                
                # CORRECTED PROTOCOL: Send key UP with element duration we just completed
                if not protocol.send_packet(False, element_duration):
                    print("\n[TCP-TS] Send failed - connection lost")
                    if sidetone:
                        sidetone.set_key(False)
                    return False
                packet_count += 1
                
                if debug:
                    timestamp_ms = int((time.time() - protocol.transmission_start) * 1000)
                    print(f"[SEND] UP (element: {element_duration}ms, ts={timestamp_ms}ms)")
                
                # Turn off sidetone
                if sidetone:
                    sidetone.set_key(False)
                
                # Determine and wait for spacing after this element
                if i < len(morse) - 1:
                    # Inter-element space (1 dit unit)
                    spacing_duration = element_space_ms
                else:
                    # Letter space (3 dit units)
                    spacing_duration = char_space_ms
                
                # Wait for spacing
                time.sleep(spacing_duration / 1000.0)
                
                # Store for next iteration
                previous_spacing_ms = spacing_duration
            
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


def load_config():
    """Load configuration from file with precedence: user home > script dir"""
    config = configparser.ConfigParser()
    
    # Try config file locations (in order of precedence)
    config_paths = [
        os.path.expanduser('~/.cw_sender.ini'),  # User home (highest priority)
        os.path.join(os.path.dirname(__file__), 'cw_sender.ini'),  # Script directory
    ]
    
    config_loaded = None
    for path in config_paths:
        if os.path.exists(path):
            config.read(path)
            config_loaded = path
            break
    
    return config, config_loaded


def main():
    # Load config file first
    config, config_path = load_config()
    
    # Extract defaults from config (if available)
    defaults = {}
    if config.has_section('network'):
        defaults['host'] = config.get('network', 'host', fallback=None)
    else:
        defaults['host'] = None
    
    if config.has_section('keyer'):
        defaults['wpm'] = config.getint('keyer', 'wpm', fallback=25)
    else:
        defaults['wpm'] = 25
    
    if config.has_section('audio'):
        defaults['no_audio'] = not config.getboolean('audio', 'enabled', fallback=True)
    else:
        defaults['no_audio'] = False
    
    if config.has_section('debug'):
        defaults['debug'] = config.getboolean('debug', 'verbose', fallback=False)
    else:
        defaults['debug'] = False
    
    # Create argument parser
    parser = argparse.ArgumentParser(
        description='CW Automated Sender TCP with Timestamps',
        epilog="""
Examples:
  # Using config file
  python3 cw_auto_sender_tcp_ts.py 25 "PARIS PARIS PARIS"
  
  # Specify host
  python3 cw_auto_sender_tcp_ts.py 192.168.1.100 25 "PARIS PARIS PARIS"
  
  # With debug
  python3 cw_auto_sender_tcp_ts.py localhost 25 "TEST" --debug

Config file locations (in order of precedence):
  1. ~/.cw_sender.ini (user home)
  2. ./cw_sender.ini (script directory)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Make host optional if it's in config
    if defaults['host']:
        parser.add_argument('host', nargs='?', default=defaults['host'],
                          help=f"Receiver hostname or IP (default from config: {defaults['host']})")
    else:
        parser.add_argument('host', help='Receiver hostname or IP')
    
    parser.add_argument('wpm', type=int, default=defaults['wpm'], nargs='?',
                       help=f"Words per minute (12-35, default: {defaults['wpm']})")
    parser.add_argument('text', nargs='?', default='PARIS PARIS PARIS',
                       help='Text to send (default: "PARIS PARIS PARIS")')
    parser.add_argument('--no-audio', action='store_true', default=defaults['no_audio'],
                       help='Disable audio sidetone')
    parser.add_argument('--debug', action='store_true', default=defaults['debug'],
                       help='Enable debug output with timestamps')
    
    args = parser.parse_args()
    
    # Show config info if loaded
    if config_path:
        print(f"✓ Loaded config from: {config_path}")
        if args.debug:
            print(f"  Host: {args.host}")
            print(f"  WPM: {args.wpm}")
        print()
    
    # Validate WPM
    if not 12 <= args.wpm <= 35:
        print("Error: WPM must be between 12 and 35")
        return 1
    
    # Send text
    success = send_text_tcp_ts(
        args.text,
        host=args.host,
        wpm=args.wpm,
        enable_audio=not args.no_audio,
        debug=args.debug
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
