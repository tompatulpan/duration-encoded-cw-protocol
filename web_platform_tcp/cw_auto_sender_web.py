#!/usr/bin/env python3
"""
CW Automated Sender - Web Platform (WebSocket)
Send text as CW over WebSocket to web platform with timestamp protocol

Usage:
    python3 cw_auto_sender_web.py [text] [options]

Examples:
    # Using config file
    python3 cw_auto_sender_web.py "CQ CQ CQ DE SM5ABC K"
    
    # Specify all parameters
    python3 cw_auto_sender_web.py "TEST" --server wss://cw-relay.workers.dev --callsign SM5ABC --wpm 25
    
    # Different room
    python3 cw_auto_sender_web.py "CQ" --room contest
"""

import sys
import os
import json
import asyncio
import websockets
import time
import argparse
import configparser
import threading

# Try to import audio library
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


class SidetoneGenerator:
    """Generate audio sidetone with improved signal quality"""
    
    def __init__(self, frequency=600, sample_rate=48000, device_index=None):
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.volume = 0.3
        
        if not AUDIO_AVAILABLE:
            raise ImportError("PyAudio not available")
        
        try:
            self.audio = pyaudio.PyAudio()
            
            # If no device specified, try pipewire/pulseaudio first
            if device_index is None:
                # Find pipewire or default device
                for i in range(self.audio.get_device_count()):
                    info = self.audio.get_device_info_by_index(i)
                    name = info['name'].lower()
                    if 'pipewire' in name or 'pulse' in name or info['name'] == 'default':
                        device_index = i
                        break
            
            self.stream = self.audio.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=sample_rate,
                output=True,
                output_device_index=device_index,
                frames_per_buffer=128  # Low latency (~2.6ms at 48kHz)
            )
            
        except Exception as e:
            print(f"[AUDIO ERROR] Failed to open audio stream: {e}")
            raise
        
        self.phase = 0.0
        self.key_down = False
        self.envelope = 0.0
        self.target_envelope = 0.0
        
        # Envelope shaping to prevent clicks (optimized for CW)
        self.rise_time = 0.004  # 4ms - fast, clean attack
        self.fall_time = 0.004  # 4ms - fast, clean release
        
        # Simple low-pass filter state for smoother audio
        self.filter_state = 0.0
        self.filter_alpha = 0.1  # Low-pass filter coefficient
        
        # Start audio generation thread
        self.running = True
        self.audio_thread = threading.Thread(target=self._audio_loop)
        self.audio_thread.daemon = True
        self.audio_thread.start()
    
    def _audio_loop(self):
        """Audio generation thread with optimized signal generation"""
        chunk_size = 128  # Match frames_per_buffer for consistency
        
        # Pre-calculate constants
        phase_increment = self.frequency / self.sample_rate
        rise_rate = 1.0 / (self.rise_time * self.sample_rate)
        fall_rate = 1.0 / (self.fall_time * self.sample_rate)
        two_pi = 2.0 * np.pi
        
        while self.running:
            # Generate audio chunk
            samples = np.zeros(chunk_size, dtype=np.float32)
            
            for i in range(chunk_size):
                # Update target envelope based on key state
                self.target_envelope = 1.0 if self.key_down else 0.0
                
                # Smooth envelope transition (exponential attack/release)
                if self.key_down:
                    # Attack (key down)
                    self.envelope = min(self.envelope + rise_rate, self.target_envelope)
                else:
                    # Release (key up)
                    self.envelope = max(self.envelope - fall_rate, self.target_envelope)
                
                # Generate sine wave only when envelope > 0 (CPU optimization)
                if self.envelope > 0.0001:
                    raw_sample = np.sin(two_pi * self.phase) * self.envelope * self.volume
                    
                    # Simple low-pass filter to smooth audio (reduces high-freq artifacts)
                    self.filter_state += self.filter_alpha * (raw_sample - self.filter_state)
                    samples[i] = self.filter_state
                    
                    # Advance phase
                    self.phase += phase_increment
                    if self.phase >= 1.0:
                        self.phase -= 1.0
                else:
                    samples[i] = 0.0
                    self.filter_state = 0.0  # Reset filter when silent
            
            # Output audio
            try:
                self.stream.write(samples.tobytes())
            except:
                pass
    
    def set_key(self, key_down):
        """Set key state"""
        self.key_down = key_down
    
    def close(self):
        """Cleanup"""
        if not AUDIO_AVAILABLE:
            return
        
        self.running = False
        if hasattr(self, 'audio_thread'):
            self.audio_thread.join(timeout=1.0)
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        if hasattr(self, 'audio'):
            self.audio.terminate()


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


class AutoWebSender:
    """Automated text-to-CW sender via WebSocket"""
    
    def __init__(self, server_url, callsign, room_id='main', wpm=25, 
                 enable_sidetone=True, debug=False):
        self.server_url = server_url
        self.callsign = callsign
        self.room_id = room_id
        self.wpm = wpm
        self.enable_sidetone = enable_sidetone
        self.debug = debug
        
        # Calculate timing
        self.dit_ms = int(1200 / wpm)
        self.dah_ms = self.dit_ms * 3
        self.element_space_ms = self.dit_ms
        self.char_space_ms = self.dit_ms * 3
        self.word_space_ms = self.dit_ms * 7
        
        # Initialize sidetone
        self.sidetone = None
        if enable_sidetone and AUDIO_AVAILABLE:
            try:
                self.sidetone = SidetoneGenerator(frequency=600)
                print("[AUDIO] Sidetone enabled (600 Hz)")
            except Exception as e:
                print(f"[AUDIO] Failed: {e}")
        
        # State tracking
        self.ws = None
        self.sequence_number = 0
        self.transmission_start = None
        self.events_sent = 0
    
    def get_timestamp_ms(self):
        """Get timestamp in milliseconds since transmission start"""
        if self.transmission_start is None:
            self.transmission_start = time.time()
            return 0
        return int((time.time() - self.transmission_start) * 1000)
    
    async def send_event(self, key_down, duration_ms):
        """Send CW event via WebSocket"""
        timestamp_ms = self.get_timestamp_ms()
        
        event = {
            'type': 'cw_event',
            'callsign': self.callsign,
            'key_down': key_down,
            'duration_ms': duration_ms,
            'timestamp_ms': timestamp_ms,
            'sequence': self.sequence_number
        }
        
        await self.ws.send(json.dumps(event))
        self.sequence_number = (self.sequence_number + 1) % 256
        self.events_sent += 1
        
        if self.debug:
            state = 'DOWN' if key_down else 'UP'
            print(f"[SEND] {state} {duration_ms}ms (ts={timestamp_ms}ms, seq={event['sequence']})")
    
    async def send_text(self, text):
        """Send text as CW"""
        print(f"\nSending: '{text}' at {self.wpm} WPM")
        print(f"Timing: dit={self.dit_ms}ms, dah={self.dah_ms}ms")
        print("=" * 60)
        
        previous_spacing_ms = 0  # Track spacing before current element
        
        for char in text.upper():
            if char not in MORSE_TABLE:
                continue
            
            morse = MORSE_TABLE[char]
            
            if char == ' ':
                # Word space - just sleep extra time beyond letter space
                await asyncio.sleep((self.word_space_ms - self.char_space_ms) / 1000.0)
                previous_spacing_ms = self.word_space_ms  # Update for next character
                print('  ', end='', flush=True)
                continue
            
            # Send morse pattern for character
            for i, symbol in enumerate(morse):
                # Determine element duration
                element_duration = self.dah_ms if symbol == '-' else self.dit_ms
                
                # CORRECTED PROTOCOL: Send key DOWN with PREVIOUS spacing duration
                await self.send_event(True, previous_spacing_ms)
                
                # Turn on sidetone
                if self.sidetone:
                    self.sidetone.set_key(True)
                
                print(symbol, end='', flush=True)
                
                # Wait for element duration
                await asyncio.sleep(element_duration / 1000.0)
                
                # CORRECTED PROTOCOL: Send key UP with element duration we just completed
                await self.send_event(False, element_duration)
                
                # Turn off sidetone
                if self.sidetone:
                    self.sidetone.set_key(False)
                
                # Determine and wait for spacing after this element
                if i < len(morse) - 1:
                    # Inter-element space
                    spacing_duration = self.element_space_ms
                else:
                    # Letter space
                    spacing_duration = self.char_space_ms
                
                # Wait for spacing
                await asyncio.sleep(spacing_duration / 1000.0)
                
                # Store for next iteration
                previous_spacing_ms = spacing_duration
            
            print(' ', end='', flush=True)  # Space after character
        
        print()  # Newline at end
    
    async def run(self, text):
        """Main run loop"""
        print("=" * 60)
        print("CW Automated Sender - Web Platform")
        print("=" * 60)
        print(f"Server:   {self.server_url}")
        print(f"Callsign: {self.callsign}")
        print(f"Room:     {self.room_id}")
        print(f"WPM:      {self.wpm}")
        print("=" * 60)
        
        try:
            # Connect to WebSocket
            print(f"\nConnecting to {self.server_url}...")
            async with websockets.connect(self.server_url) as ws:
                self.ws = ws
                print("✓ Connected")
                
                # Send join message
                join_msg = {
                    'type': 'join',
                    'callsign': self.callsign,
                    'room': self.room_id
                }
                await ws.send(json.dumps(join_msg))
                print(f"✓ Joined room: {self.room_id}")
                
                # Send text
                start_time = time.time()
                await self.send_text(text)
                duration = time.time() - start_time
                
                # Wait a bit for final events to be processed
                await asyncio.sleep(0.5)
                
                print(f"\n--- Statistics ---")
                print(f"Duration: {duration:.1f}s")
                print(f"Events sent: {self.events_sent}")
                print(f"✓ Transmission complete")
                
        except websockets.exceptions.WebSocketException as e:
            print(f"\n[ERROR] WebSocket error: {e}")
            return False
        except Exception as e:
            print(f"\n[ERROR] {e}")
            return False
        finally:
            if self.sidetone:
                self.sidetone.close()
        
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
    if config.has_section('web_platform'):
        defaults['server'] = config.get('web_platform', 'server', fallback=None)
        defaults['room'] = config.get('web_platform', 'room', fallback='main')
    else:
        defaults['server'] = None
        defaults['room'] = 'main'
    
    if config.has_section('operator'):
        defaults['callsign'] = config.get('operator', 'callsign', fallback=None)
    else:
        defaults['callsign'] = None
    
    if config.has_section('keyer'):
        defaults['wpm'] = config.getint('keyer', 'wpm', fallback=25)
    else:
        defaults['wpm'] = 25
    
    if config.has_section('audio'):
        defaults['no_sidetone'] = not config.getboolean('audio', 'enabled', fallback=True)
    else:
        defaults['no_sidetone'] = False
    
    if config.has_section('debug'):
        defaults['debug'] = config.getboolean('debug', 'verbose', fallback=False)
    else:
        defaults['debug'] = False
    
    # Create argument parser
    parser = argparse.ArgumentParser(
        description='CW Automated Sender - Web Platform (WebSocket)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using config file
  python3 cw_auto_sender_web.py "CQ CQ CQ DE SM5ABC K"
  
  # Override settings
  python3 cw_auto_sender_web.py "TEST" --wpm 30 --room contest
  
  # Specify all parameters
  python3 cw_auto_sender_web.py "CQ" --server wss://cw-relay.workers.dev --callsign SM5ABC

Config file locations (in order of precedence):
  1. ~/.cw_sender.ini (user home)
  2. ./cw_sender.ini (script directory)
        """
    )
    
    parser.add_argument('text', nargs='?', default='PARIS PARIS PARIS',
                       help='Text to send (default: "PARIS PARIS PARIS")')
    
    # Make server and callsign optional if they're in config
    parser.add_argument('--server',
                        required=(defaults['server'] is None),
                        default=defaults['server'],
                        help='WebSocket server URL (e.g., wss://cw-relay.workers.dev)')
    parser.add_argument('--callsign',
                        required=(defaults['callsign'] is None),
                        default=defaults['callsign'],
                        help='Your callsign')
    parser.add_argument('--room', default=defaults['room'],
                       help=f"Room ID (default: {defaults['room']})")
    parser.add_argument('--wpm', type=int, default=defaults['wpm'],
                       help=f"Words per minute (default: {defaults['wpm']})")
    parser.add_argument('--no-sidetone', action='store_true', default=defaults['no_sidetone'],
                       help='Disable sidetone audio')
    parser.add_argument('--debug', action='store_true', default=defaults['debug'],
                       help='Enable debug output')
    
    args = parser.parse_args()
    
    # Show config info if loaded
    if config_path:
        print(f"✓ Loaded config from: {config_path}")
        if args.debug:
            print(f"  Server: {args.server}")
            print(f"  Callsign: {args.callsign}")
            print(f"  Room: {args.room}")
            print(f"  WPM: {args.wpm}")
        print()
    
    # Check audio availability
    if not args.no_sidetone and not AUDIO_AVAILABLE:
        print("\n⚠ Warning: pyaudio not available")
        print("  Install with: pip3 install pyaudio")
        print("  Continuing without sidetone...\n")
    
    # Create sender
    sender = AutoWebSender(
        server_url=args.server,
        callsign=args.callsign,
        room_id=args.room,
        wpm=args.wpm,
        enable_sidetone=not args.no_sidetone,
        debug=args.debug
    )
    
    # Run
    try:
        success = asyncio.run(sender.run(args.text))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n✓ Stopped by user")
        sys.exit(0)


if __name__ == '__main__':
    main()
