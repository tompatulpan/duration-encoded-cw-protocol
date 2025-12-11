#!/usr/bin/env python3
"""
USB Key Sender with FEC - Read physical CW key via USB serial adapter with Forward Error Correction
Supports: Straight key, Bug, Iambic Mode A, Iambic Mode B
"""

import socket
import time
import sys
import threading
import serial
import serial.tools.list_ports
from cw_protocol_fec import CWProtocolFEC
try:
    import pyaudio
    import numpy as np
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


# Import MorseDecoder and IambicKeyer from standard version
from cw_usb_key_sender_with_decoder import MorseDecoder, IambicKeyer


class USBKeySenderFEC:
    """Read CW key from USB serial port control lines with FEC"""
    
    def __init__(self, host='localhost', port=7355, serial_port='/dev/ttyUSB0', 
                 mode='straight', wpm=20, keyer_mode='B', sidetone=False, sidetone_freq=600,
                 decode=True):
        """
        Initialize USB key sender with FEC
        
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
        self.protocol = CWProtocolFEC()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host = host
        self.port = port
        self.mode = mode
        self.wpm = wpm
        
        # FEC buffer for batching packets
        self.packet_buffer = []
        self.buffer_lock = threading.Lock()
        self.packets_in_block = 0  # Track data packets sent in current block
        self.last_packet_time = time.time()  # Track time of last packet for timeout flush
        
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
        
        # Note: No timeout flush needed - data packets sent immediately,
        # FEC sent after 10 packets or on EOT
        
        # Adaptive EOT timeout: ~2 seconds of silence triggers EOT
        # This is approximately 40 dit times
        if mode == 'iambic':
            dit_duration = 1200 / wpm  # ms
            self.eot_timeout = (40 * dit_duration) / 1000.0  # seconds (~1.9s at 25 WPM)
        else:
            self.eot_timeout = 2.0  # Straight key: fixed 2 seconds
        
        print("=" * 60)
        print(f"USB CW Key Sender with FEC - {mode.upper()} mode")
        if mode == 'iambic':
            print(f"Iambic Mode {keyer_mode} - {wpm} WPM")
        print(f"Serial port: {serial_port}")
        print(f"Sending to {host}:{port}")
        print(f"FEC: Reed-Solomon (10 data + 6 redundancy packets)")
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
        """Send a single CW event with FEC"""
        # Create packet with FEC
        packet, fec_packets = self.protocol.create_packet_fec(
            key_down=key_down,
            duration_ms=int(duration_ms)
        )
        
        # Send data packet immediately
        self.sock.sendto(packet, (self.host, self.port))
        
        # Buffer the FEC packets and track data packet count
        with self.buffer_lock:
            self.packet_buffer.extend(fec_packets)
            self.packets_in_block += 1
            self.last_packet_time = time.time()
            
            # If we've sent a full block (10 data packets), flush FEC
            if self.packets_in_block >= self.protocol.FEC_BLOCK_SIZE:
                # Send FEC packets (we're already holding the lock)
                for fec_pkt in self.packet_buffer:
                    self.sock.sendto(fec_pkt, (self.host, self.port))
                self.packet_buffer.clear()
                self.packets_in_block = 0
        
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
    
    def _flush_fec_buffer(self):
        """Send all buffered FEC packets"""
        with self.buffer_lock:
            if self.packet_buffer:
                for fec_pkt in self.packet_buffer:
                    self.sock.sendto(fec_pkt, (self.host, self.port))
                self.packet_buffer.clear()
                self.packets_in_block = 0
    
    def _send_eot(self):
        """Send EOT and flush any remaining FEC packets"""
        # Flush any remaining FEC packets
        self._flush_fec_buffer()
        
        # Send EOT
        eot_packet = self.protocol.create_eot_packet()
        self.sock.sendto(eot_packet, (self.host, self.port))
        self.eot_sent = True
        print()
        print("[EOT]", flush=True)
    
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
                    
                    self._send_eot()
            
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
                    
                    self._send_eot()
                
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
            
            # Flush any remaining FEC packets
            self._flush_fec_buffer()
            
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
        print("USB CW Key Sender with FEC and Decoder")
        print("=" * 60)
        print("\nUsage:")
        print("  python3 cw_usb_key_sender_with_decoder_fec.py <host> [mode] [wpm] [serial_port] [options]")
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
        print("\nFEC (Forward Error Correction):")
        print("  - Reed-Solomon (10 data + 6 redundancy packets)")
        print("  - Recovers up to 3 lost packets per block")
        print("  - Recommended for WiFi/cellular/internet links")
        print("\nExamples:")
        print("  python3 cw_usb_key_sender_with_decoder_fec.py localhost")
        print("  python3 cw_usb_key_sender_with_decoder_fec.py localhost iambic-b 25")
        print("  python3 cw_usb_key_sender_with_decoder_fec.py 192.168.1.100 straight --no-decode")
        print("  python3 cw_usb_key_sender_with_decoder_fec.py localhost iambic-b 20 /dev/ttyUSB1")
        print("  python3 cw_usb_key_sender_with_decoder_fec.py localhost iambic-b 20 /dev/ttyUSB0 --sidetone-freq 700")
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
    sender = USBKeySenderFEC(
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
