#!/usr/bin/env python3
"""
USB Key Sender - Read physical CW key via USB serial adapter
Supports: Straight key, Bug, Iambic Mode A, Iambic Mode B
"""

import socket
import time
import sys
import threading
import serial
import serial.tools.list_ports
from cw_protocol import CWProtocol
try:
    import pyaudio
    import numpy as np
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


class MorseDecoder:
    """Decode CW timing into text characters"""
    
    # International Morse Code table
    MORSE_CODE = {
        '.-': 'A',    '-...': 'B',  '-.-.': 'C',  '-..': 'D',
        '.': 'E',     '..-.': 'F',  '--.': 'G',   '....': 'H',
        '..': 'I',    '.---': 'J',  '-.-': 'K',   '.-..': 'L',
        '--': 'M',    '-.': 'N',    '---': 'O',   '.--.': 'P',
        '--.-': 'Q',  '.-.': 'R',   '...': 'S',   '-': 'T',
        '..-': 'U',   '...-': 'V',  '.--': 'W',   '-..-': 'X',
        '-.--': 'Y',  '--..': 'Z',
        
        '-----': '0', '.----': '1', '..---': '2', '...--': '3',
        '....-': '4', '.....': '5', '-....': '6', '--...': '7',
        '---..': '8', '----.': '9',
        
        '.-.-.-': '.', '--..--': ',', '..--..': '?', '.----.': "'",
        '-.-.--': '!', '-..-.': '/', '-.--.': '(', '-.--.-': ')',
        '.-...': '&', '---...': ':', '-.-.-.': ';', '-...-': '=',
        '.-.-.': '+', '-....-': '-', '..--.-': '_', '.-..-.': '"',
        '...-..-': '$', '.--.-.': '@', 
        
        # Prosigns (procedural signals)
        '...---...': '<SOS>',   # Distress signal
        '.-.-.': '<AR>',        # End of message
        '-...-.-': '<BT>',      # New paragraph/pause
        '........': '<HH>',     # Error correction
        '-.--.': '<KN>',        # Invite specific station
        '...-.-': '<SK>',       # End of contact
        '-.-.-': '<KA>',        # Start of transmission
        '-.-.-': '<CT>'         # Start of transmission (alternate)
    }
    
    def __init__(self, wpm=20):
        """
        Initialize decoder
        
        Args:
            wpm: Speed in WPM (used for timing thresholds)
        """
        self.wpm = wpm
        self.dit_duration = 1200 / wpm  # ms
        self.current_pattern = ""
        self.decoded_text = ""
        self.last_element_time = None
        self.last_key_down_duration = 0  # Track last dit/dah duration
        self.last_spacing_check = 0  # Track when we last checked spacing
        
        # Timing thresholds (in milliseconds)
        self.dit_threshold = self.dit_duration * 1.5  # < 1.5 dits = dit
        self.char_space = self.dit_duration * 2.5     # ~2.5 dit spaces = character boundary
        self.word_space = self.dit_duration * 10      # ~10 dit spaces = word boundary (need longer for manual keying)
    
    def add_element(self, duration_ms):
        """
        Add a dit or dah based on key-down duration
        
        Args:
            duration_ms: Duration of key-down event
        """
        # Determine if dit or dah
        if duration_ms < self.dit_threshold:
            self.current_pattern += '.'
        else:
            self.current_pattern += '-'
        
        self.last_element_time = time.time()
        self.last_spacing_check = 0  # Reset spacing check for new element
    
    def check_spacing(self, silence_ms):
        """
        Check if silence indicates character or word boundary
        
        Args:
            silence_ms: Duration of key-up (silence) in milliseconds
            
        Returns:
            'word' - word boundary detected (returns character)
            'char' - character boundary detected (returns character)
            None - still within element spacing
        """
        if not self.current_pattern:
            return None
        
        # Prevent repeated triggering on same silence period
        if silence_ms <= self.last_spacing_check:
            return None
        
        # Word space
        if silence_ms > self.word_space:
            self.last_spacing_check = silence_ms
            char = self._finish_character()
            if char:
                self.decoded_text += ' '
                return ('word', char)
            return None
        
        # Character space
        elif silence_ms > self.char_space:
            self.last_spacing_check = silence_ms
            char = self._finish_character()
            if char:
                return ('char', char)
            return None
        
        return None
    
    def _finish_character(self):
        """Convert current pattern to character"""
        if self.current_pattern:
            char = self.MORSE_CODE.get(self.current_pattern, '?')
            self.decoded_text += char
            self.current_pattern = ""
            return char
        return None
    
    def get_decoded_text(self):
        """Get the decoded text so far"""
        return self.decoded_text
    
    def reset(self):
        """
        Finish any pending character and reset
        
        Returns:
            str: Final decoded text
        """
        if self.current_pattern:
            self._finish_character()
        result = self.decoded_text
        self.decoded_text = ""
        self.current_pattern = ""
        self.last_element_time = None
        return result


class IambicKeyer:
    """Iambic keyer logic (Mode A and Mode B) - Clean state machine based on n1gp/iambic-keyer"""
    
    # State constants
    IDLE = 0
    DIT = 1
    DAH = 2
    
    def __init__(self, wpm=20, mode='B'):
        self.mode = mode  # 'A' or 'B'
        self.set_speed(wpm)
        
        # State
        self.state = self.IDLE
        self.dit_memory = False
        self.dah_memory = False
        
    def set_speed(self, wpm):
        """Set keyer speed"""
        self.wpm = wpm
        self.dit_duration = 1200 / wpm  # ms
        self.dah_duration = self.dit_duration * 3
        self.element_space = self.dit_duration
        self.char_space = self.dit_duration * 3
    
    def update(self, dit_paddle, dah_paddle, send_element_callback):
        """
        Main keyer update - call this in a loop
        
        Args:
            dit_paddle: bool - dit paddle currently pressed
            dah_paddle: bool - dah paddle currently pressed  
            send_element_callback: function(key_down: bool, duration_ms: float)
        
        Returns:
            bool - True if keyer is active, False if idle
        """
        
        # State: IDLE - waiting for paddle press
        if self.state == self.IDLE:
            if dit_paddle:
                self.dit_memory = False
                self.dah_memory = False
                self.state = self.DIT
                # Send dit
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check if dah was pressed during dit (Mode B memory)
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
                    
            elif dah_paddle:
                self.dit_memory = False
                self.dah_memory = False
                self.state = self.DAH
                # Send dah
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check if dit was pressed during dah (Mode B memory)
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                return False  # Still idle
                
        # State: DIT - just sent a dit
        elif self.state == self.DIT:
            # Sample paddles during element space
            if dit_paddle:
                self.dit_memory = True
            if dah_paddle:
                self.dah_memory = True
                
            # Decide what's next
            if self.dah_memory:
                # Send dah next
                self.dah_memory = False
                self.state = self.DAH
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check paddle during element
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
                    
            elif dit_paddle or self.dit_memory:
                # Repeat dit
                self.dit_memory = False
                self.state = self.DIT
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
            else:
                # End of character - send extra space to complete char_space
                # (we already sent element_space after the last element)
                extra_space = self.char_space - self.element_space
                time.sleep(extra_space / 1000.0)
                self.state = self.IDLE
                
        # State: DAH - just sent a dah
        elif self.state == self.DAH:
            # Sample paddles during element space
            if dit_paddle:
                self.dit_memory = True
            if dah_paddle:
                self.dah_memory = True
                
            # Decide what's next
            if self.dit_memory:
                # Send dit next
                self.dit_memory = False
                self.state = self.DIT
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check paddle during element
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
                    
            elif dah_paddle or self.dah_memory:
                # Repeat dah
                self.dah_memory = False
                self.state = self.DAH
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                # End of character - send extra space to complete char_space
                # (we already sent element_space after the last element)
                extra_space = self.char_space - self.element_space
                time.sleep(extra_space / 1000.0)
                self.state = self.IDLE
                
        return self.state != self.IDLE


class USBKeySender:
    """Read CW key from USB serial port control lines"""
    
    def __init__(self, host='localhost', port=7355, serial_port='/dev/ttyUSB0', 
                 mode='straight', wpm=20, keyer_mode='B', sidetone=False, sidetone_freq=600,
                 decode=True):
        """
        Initialize USB key sender
        
        Args:
            host: Target host
            port: Target UDP port
            serial_port: Serial port device (e.g., /dev/ttyUSB0, COM3)
            mode: 'straight', 'bug', 'iambic' (iambic includes mode A/B)
            wpm: Speed in WPM (for keyer modes)
            keyer_mode: 'A' or 'B' for iambic keyer
            sidetone: Enable local audio sidetone
            sidetone_freq: Sidetone frequency in Hz
            decode: Enable CW-to-text decoding
        """
        self.protocol = CWProtocol()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host = host
        self.port = port
        self.mode = mode
        self.wpm = wpm
        
        # Decoder setup
        self.decode_enabled = decode
        self.decoder = MorseDecoder(wpm=wpm) if decode else None
        
        # Sidetone setup
        self.sidetone_enabled = False
        self.sidetone_freq = sidetone_freq
        self.audio = None
        self.stream = None
        self.sidetone_on = False
        self.phase = 0.0
        self.sidetone_error = None
        
        if sidetone and PYAUDIO_AVAILABLE:
            try:
                self.audio = pyaudio.PyAudio()
                self.stream = self.audio.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=48000,
                    output=True,
                    frames_per_buffer=512,
                    stream_callback=self._audio_callback
                )
                self.stream.start_stream()
                self.sidetone_enabled = True
            except Exception as e:
                self.sidetone_error = str(e)
                if self.audio:
                    self.audio.terminate()
                self.audio = None
                self.stream = None
        
        # Open serial port
        self.serial = serial.Serial(serial_port, baudrate=9600, timeout=0)
        
        # Iambic keyer (if needed)
        self.keyer = None
        if mode == 'iambic':
            self.keyer = IambicKeyer(wpm=wpm, mode=keyer_mode)
        
        self.running = False
        self.last_dit_state = False
        self.last_dah_state = False
        self.last_change_time = time.time()
        self.last_key_up_time = time.time()
        self.eot_sent = False
        
        # Adaptive EOT timeout: ~2 seconds of silence triggers EOT
        # This is approximately 40 dit times
        if mode == 'iambic':
            dit_duration = 1200 / wpm  # ms
            self.eot_timeout = (40 * dit_duration) / 1000.0  # seconds (~1.9s at 25 WPM)
        else:
            self.eot_timeout = 2.0  # Straight key: fixed 2 seconds
        
        print("=" * 60)
        print(f"USB CW Key Sender - {mode.upper()} mode")
        if mode == 'iambic':
            print(f"Iambic Mode {keyer_mode} - {wpm} WPM")
        print(f"Serial port: {serial_port}")
        print(f"Sending to {host}:{port}")
        if self.sidetone_enabled:
            print(f"TX Sidetone: {self.sidetone_freq} Hz")
        else:
            if not PYAUDIO_AVAILABLE:
                print("TX Sidetone: disabled (PyAudio not available)")
            elif self.sidetone_error:
                print(f"TX Sidetone: disabled (Error: {self.sidetone_error})")
            else:
                print("TX Sidetone: disabled")
        print("=" * 60)
        print("\nPin assignments:")
        if mode == 'straight':
            print("  CTS (pin 8) -> Key tip")
            print("  GND (pin 5) -> Key ring")
        elif mode == 'iambic':
            print("  CTS (pin 8) -> Dit paddle")
            print("  DSR (pin 6) -> Dah paddle")
            print("  GND (pin 5) -> Common")
        print("\nPress Ctrl+C to quit")
        print("-" * 60)
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Generate sidetone audio"""
        if self.sidetone_on:
            # Generate sine wave
            samples = np.arange(frame_count)
            omega = 2.0 * np.pi * self.sidetone_freq / 48000
            audio = 0.3 * np.sin(omega * samples + self.phase).astype(np.float32)
            self.phase = (self.phase + omega * frame_count) % (2.0 * np.pi)
        else:
            # Silence
            audio = np.zeros(frame_count, dtype=np.float32)
        
        return (audio.tobytes(), pyaudio.paContinue)
    
    def send_event(self, key_down, duration_ms):
        """Send a single CW event"""
        packet = self.protocol.create_packet(
            key_down=key_down,
            duration_ms=int(duration_ms)
        )
        self.sock.sendto(packet, (self.host, self.port))
        
        # Control sidetone
        if self.sidetone_enabled:
            self.sidetone_on = key_down
        
        # Decode CW
        if self.decode_enabled and self.decoder:
            if key_down:
                # Key down - add the element (dit/dah) based on duration
                self.decoder.add_element(duration_ms)
            # For iambic mode, spacing detection is handled in the poll loop
            # For straight key mode, check spacing on key-up events
            elif not hasattr(self, 'keyer') or self.keyer is None:
                # Straight key mode - check spacing based on key-up duration
                spacing = self.decoder.check_spacing(duration_ms)
                if spacing:
                    spacing_type, char = spacing
                    if spacing_type == 'char':
                        # Character completed - print it
                        print(char, end='', flush=True)
                    elif spacing_type == 'word':
                        # Word boundary - add space
                        print(f"{char} ", end='', flush=True)
        else:
            # Original visual feedback (dots and dashes)
            if key_down:
                print("▬" if duration_ms > 100 else "▪", end='', flush=True)
    
    def poll_straight_key(self):
        """Poll straight key on CTS line"""
        while self.running:
            # Read CTS line
            key_down = self.serial.cts
            current_time = time.time()
            
            if key_down != self.last_dit_state:
                duration_ms = int((current_time - self.last_change_time) * 1000)
                
                self.send_event(key_down, duration_ms)
                
                self.last_dit_state = key_down
                self.last_change_time = current_time
                
                if not key_down:
                    self.last_key_up_time = current_time
                    self.eot_sent = False
            
            # Send EOT after adaptive timeout
            if not key_down and not self.eot_sent:
                silence_time = current_time - self.last_key_up_time
                
                # Check for character/word spacing during silence (before EOT)
                if self.decode_enabled and self.decoder and silence_time < self.eot_timeout:
                    silence_ms = silence_time * 1000
                    spacing = self.decoder.check_spacing(silence_ms)
                    if spacing:
                        spacing_type, char = spacing
                        if spacing_type == 'char':
                            print(char, end='', flush=True)
                        elif spacing_type == 'word':
                            print(f"{char} ", end='', flush=True)
                
                if silence_time > self.eot_timeout:
                    # Finish any pending decoded text
                    if self.decode_enabled and self.decoder:
                        char = self.decoder._finish_character()
                        if char:
                            print(char, end='', flush=True)
                    
                    eot_packet = self.protocol.create_eot_packet()
                    self.sock.sendto(eot_packet, (self.host, self.port))
                    self.eot_sent = True
                    print()
                    print("[EOT]", flush=True)
            
            time.sleep(0.002)  # 500 Hz polling
    
    def poll_iambic_keyer(self):
        """Poll iambic paddles and generate keyer output"""
        while self.running:
            # Read both paddles
            dit_pressed = self.serial.cts  # CTS = dit paddle
            dah_pressed = self.serial.dsr  # DSR = dah paddle
            current_time = time.time()
            
            # Update keyer logic
            active = self.keyer.update(dit_pressed, dah_pressed, self.send_event)
            
            if not active:
                # Track idle time and send EOT
                if not hasattr(self, 'last_keyer_active'):
                    self.last_keyer_active = current_time
                    self.eot_sent = False
                    self.char_printed = False  # Track if we've printed the character
                    self.word_space_printed = False  # Track if we've printed word space
                
                silence_time = current_time - self.last_keyer_active
                
                # Check for character/word spacing during silence (before EOT)
                if self.decode_enabled and self.decoder and silence_time < self.eot_timeout:
                    silence_ms = silence_time * 1000
                    
                    # Wait 200ms before printing character to allow natural CW rhythm
                    if self.decoder.current_pattern and not self.char_printed and silence_ms > 200:
                        # Print the character after 200ms delay
                        char = self.decoder._finish_character()
                        if char:
                            print(char, end='', flush=True)
                        self.char_printed = True
                    
                    # Check for word boundary (longer pause) and add space if needed
                    if self.char_printed and not self.word_space_printed and silence_ms > self.decoder.word_space:
                        print(' ', end='', flush=True)
                        self.decoder.decoded_text += ' '
                        self.word_space_printed = True
                
                if silence_time > self.eot_timeout and not self.eot_sent:
                    # Finish any pending decoded text
                    if self.decode_enabled and self.decoder:
                        char = self.decoder._finish_character()
                        if char:
                            print(char, end='', flush=True)
                    
                    eot_packet = self.protocol.create_eot_packet()
                    self.sock.sendto(eot_packet, (self.host, self.port))
                    self.eot_sent = True
                    print()
                    print("[EOT]", flush=True)
                
                # Small delay when idle
                time.sleep(0.005)  # 200 Hz when idle
            else:
                self.last_keyer_active = current_time
                self.eot_sent = False
                if hasattr(self, 'char_printed'):
                    self.char_printed = False  # Reset when active
                    self.word_space_printed = False  # Reset word space flag
    
    def run(self):
        """Start reading key and sending events"""
        self.running = True
        
        try:
            if self.mode == 'straight' or self.mode == 'bug':
                self.poll_straight_key()
            elif self.mode == 'iambic':
                self.poll_iambic_keyer()
                
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        finally:
            self.running = False
            if self.sidetone_enabled:
                self.stream.stop_stream()
                self.stream.close()
                self.audio.terminate()
            self.serial.close()
            self.sock.close()
            print("73!")


def list_serial_ports():
    """List available serial ports"""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No serial ports found!")
        return None
    
    print("\nAvailable serial ports:")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port.device}")
        print(f"      {port.description}")
        if port.hwid:
            print(f"      {port.hwid}")
    
    return ports


def main():
    if len(sys.argv) < 2:
        print("USB CW Key Sender with Decoder")
        print("=" * 60)
        print("\nUsage:")
        print("  python3 cw_usb_key_sender_with_decoder.py <host> [mode] [wpm] [serial_port] [options]")
        print("\nModes:")
        print("  straight    - Straight key (default)")
        print("  bug         - Semi-automatic bug")
        print("  iambic-a    - Iambic Mode A")
        print("  iambic-b    - Iambic Mode B (default for iambic)")
        print("\nOptions:")
        print("  --decode                - Decode CW to text (default)")
        print("  --no-decode             - Show dots/dashes only")
        print("  --sidetone              - Enable TX sidetone (default)")
        print("  --no-sidetone           - Disable TX sidetone")
        print("  --sidetone-freq <Hz>    - Sidetone frequency (default: 600)")
        print("\nExamples:")
        print("  python3 cw_usb_key_sender_with_decoder.py localhost")
        print("  python3 cw_usb_key_sender_with_decoder.py localhost iambic-b 25")
        print("  python3 cw_usb_key_sender_with_decoder.py 192.168.1.100 straight --no-decode")
        print("  python3 cw_usb_key_sender_with_decoder.py localhost iambic-b 20 /dev/ttyUSB1")
        print("  python3 cw_usb_key_sender_with_decoder.py localhost iambic-b 20 /dev/ttyUSB0 --sidetone-freq 700")
        print()
        
        # List available ports
        list_serial_ports()
        return 1
    
    # Parse arguments
    host = sys.argv[1]
    mode_arg = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 'straight'
    wpm = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 20
    serial_port = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith('--') else None
    
    # Parse options
    sidetone = True
    sidetone_freq = 600
    decode = True  # Enable decoding by default
    for i, arg in enumerate(sys.argv):
        if arg == '--no-sidetone':
            sidetone = False
        elif arg == '--sidetone':
            sidetone = True
        elif arg == '--sidetone-freq' and i + 1 < len(sys.argv):
            sidetone_freq = int(sys.argv[i + 1])
        elif arg == '--decode':
            decode = True
        elif arg == '--no-decode':
            decode = False
    
    # Parse mode
    if mode_arg.startswith('iambic'):
        mode = 'iambic'
        keyer_mode = 'B' if mode_arg == 'iambic-b' or mode_arg == 'iambic' else 'A'
    else:
        mode = mode_arg
        keyer_mode = 'B'
    
    # Auto-detect serial port if not specified
    if not serial_port:
        ports = list_serial_ports()
        if not ports:
            return 1
        
        if len(ports) == 1:
            serial_port = ports[0].device
            print(f"\nAuto-selected: {serial_port}")
        else:
            choice = int(input("\nSelect port number: "))
            serial_port = ports[choice].device
    
    # Create sender
    sender = USBKeySender(
        host=host,
        port=7355,
        serial_port=serial_port,
        mode=mode,
        wpm=wpm,
        keyer_mode=keyer_mode,
        sidetone=sidetone,
        sidetone_freq=sidetone_freq,
        decode=decode
    )
    
    # Run
    sender.run()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
