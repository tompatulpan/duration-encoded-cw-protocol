#!/usr/bin/env python3
"""
USB Key Sender - TCP Timestamp Protocol
Read physical CW key via USB serial adapter and transmit using timestamp protocol
Supports: Straight key, Bug, Iambic Mode A, Iambic Mode B

Usage:
    python3 cw_usb_key_sender_tcp_ts.py <host> [options]

Examples:
    # Straight key
    python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode straight
    
    # Iambic paddles (Mode B)
    python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode iambic-b --wpm 25
    
    # Bug (mechanical keyer)
    python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode bug --wpm 20
"""

import socket
import time
import sys
import threading
import serial
import serial.tools.list_ports
import argparse
import configparser
import os
from cw_protocol_tcp_ts import CWProtocolTCPTimestamp

try:
    import pyaudio
    import numpy as np
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

# Import sidetone from cw_receiver
try:
    from cw_receiver import SidetoneGenerator
except ImportError:
    SidetoneGenerator = None


class IambicKeyer:
    """Iambic keyer logic (Mode A and Mode B)"""
    
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
                self.dah_memory = False
                self.state = self.DAH
                # Send dah
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Mode B: Check for dit during dah
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
                    
            elif self.dit_memory:
                self.dit_memory = False
                self.state = self.DIT
                # Send dit
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Mode B: Check for dah during dit
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
            else:
                # No memory, return to idle
                self.state = self.IDLE
                return False
                
        # State: DAH - just sent a dah
        elif self.state == self.DAH:
            # Sample paddles during element space
            if dit_paddle:
                self.dit_memory = True
            if dah_paddle:
                self.dah_memory = True
                
            # Decide what's next
            if self.dit_memory:
                self.dit_memory = False
                self.state = self.DIT
                # Send dit
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Mode B: Check for dah during dit
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
                    
            elif self.dah_memory:
                self.dah_memory = False
                self.state = self.DAH
                # Send dah
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Mode B: Check for dit during dah
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                # No memory, return to idle
                self.state = self.IDLE
                return False
                
        return True  # Still active


class USBKeySender:
    """USB CW Key sender using TCP timestamp protocol"""
    
    def __init__(self, host, port, mode='straight', wpm=20, serial_port=None, no_audio=False, debug=False):
        self.host = host
        self.port = port
        self.mode = mode
        self.wpm = wpm
        self.running = False
        self.no_audio = no_audio
        self.debug = debug
        
        # Protocol (will connect later)
        self.protocol = CWProtocolTCPTimestamp()
        
        # Audio sidetone
        if not no_audio and SidetoneGenerator:
            try:
                self.sidetone = SidetoneGenerator(600)  # 600 Hz TX tone
                print("[AUDIO] Sidetone enabled (600 Hz)")
            except Exception as e:
                print(f"[AUDIO] Could not initialize sidetone: {e}")
                self.sidetone = None
        else:
            self.sidetone = None
        
        # Keyer (for iambic/bug modes)
        if mode in ['iambic-a', 'iambic-b', 'bug']:
            keyer_mode = 'B' if mode == 'iambic-b' else 'A'
            self.keyer = IambicKeyer(wpm=wpm, mode=keyer_mode)
        else:
            self.keyer = None
        
        # Serial port
        self.serial_port = serial_port
        self.ser = None
        
        # Key state
        self.last_key_down = False
        self.key_down_start = None
        
    def find_serial_port(self):
        """Auto-detect USB serial adapter"""
        ports = list(serial.tools.list_ports.comports())
        
        print("\n[SERIAL] Available ports:")
        for i, port in enumerate(ports):
            print(f"  {i}: {port.device} - {port.description}")
        
        if not ports:
            print("[ERROR] No serial ports found!")
            return None
        
        if len(ports) == 1:
            print(f"\n[SERIAL] Auto-selected: {ports[0].device}")
            return ports[0].device
        
        # Ask user to select
        try:
            choice = int(input(f"\nSelect port (0-{len(ports)-1}): "))
            if 0 <= choice < len(ports):
                return ports[choice].device
        except (ValueError, KeyboardInterrupt):
            pass
        
        return None
    
    def connect_serial(self):
        """Connect to USB serial adapter"""
        if self.serial_port is None:
            self.serial_port = self.find_serial_port()
        
        if self.serial_port is None:
            return False
        
        try:
            self.ser = serial.Serial(
                self.serial_port,
                baudrate=9600,
                timeout=0.001  # Non-blocking
            )
            
            # Read initial pin states
            time.sleep(0.1)  # Let port settle
            print(f"[SERIAL] Connected to {self.serial_port}")
            print(f"[DEBUG] Initial pin states:")
            print(f"  CTS (dit): {self.ser.cts}")
            print(f"  DSR (dah): {self.ser.dsr}")
            print(f"  DCD: {self.ser.cd}")
            print(f"  RI: {self.ser.ri}")
            
            # Warn if CTS is high (probably not connected correctly)
            if self.ser.cts:
                print("[WARNING] CTS pin is HIGH - key may appear pressed!")
                print("[WARNING] Check wiring: Key should connect CTS to GND")
            
            return True
        except Exception as e:
            print(f"[ERROR] Could not open serial port: {e}")
            return False
    
    def read_key_state(self):
        """
        Read key state from serial port
        
        Returns:
            (dit_active, dah_active) for iambic/bug
            (key_down, None) for straight key
        """
        if not self.ser:
            return (False, False) if self.mode != 'straight' else (False, None)
        
        try:
            # Read CTS and DSR lines (common USB serial adapter wiring)
            # CTS = dit paddle (or key for straight key)
            # DSR = dah paddle
            dit_active = self.ser.cts
            dah_active = self.ser.dsr if self.mode != 'straight' else False
            
            return (dit_active, dah_active) if self.mode != 'straight' else (dit_active, None)
        except:
            return (False, False) if self.mode != 'straight' else (False, None)
    
    def send_event(self, key_down, duration_ms):
        """Send CW event with timestamp"""
        try:
            # Get current timestamp
            if self.protocol.transmission_start is None:
                timestamp_ms = 0
            else:
                timestamp_ms = int((time.time() - self.protocol.transmission_start) * 1000)
            
            self.protocol.send_packet(key_down, int(duration_ms))
            
            # Update sidetone
            if self.sidetone:
                self.sidetone.set_key(key_down)
            
            state_str = "DOWN" if key_down else "UP"
            if self.debug:
                print(f"[SEND] {state_str} {duration_ms:5.1f}ms (ts={timestamp_ms}ms)")
            else:
                print(f"[KEY] {state_str:4s} {duration_ms:5.1f}ms")
            
        except Exception as e:
            print(f"[ERROR] Send failed: {e}")
            self.running = False
    
    def run_straight_key(self):
        """Straight key mode - send key state changes directly"""
        print("\n[MODE] Straight key")
        print("[INFO] Press key to send CW")
        print("[INFO] Press Ctrl+C to quit\n")
        
        last_change_time = time.time()
        
        while self.running:
            key_down, _ = self.read_key_state()
            
            # Detect state change
            if key_down != self.last_key_down:
                current_time = time.time()
                duration_ms = (current_time - last_change_time) * 1000.0
                
                # Send previous state's duration
                self.send_event(self.last_key_down, duration_ms)
                
                self.last_key_down = key_down
                last_change_time = current_time
            
            time.sleep(0.001)  # 1ms poll rate
    
    def run_iambic_keyer(self):
        """Iambic keyer mode (A or B)"""
        mode_name = "Iambic Mode B" if self.mode == 'iambic-b' else "Iambic Mode A"
        print(f"\n[MODE] {mode_name} @ {self.wpm} WPM")
        print("[INFO] Dit = CTS, Dah = DSR")
        print("[INFO] Press Ctrl+C to quit\n")
        
        while self.running:
            dit_paddle, dah_paddle = self.read_key_state()
            
            # Update keyer state machine
            active = self.keyer.update(dit_paddle, dah_paddle, self.send_event)
            
            if not active:
                time.sleep(0.001)  # 1ms poll rate when idle
    
    def run_bug(self):
        """Bug mode - automatic dits, manual dahs"""
        print(f"\n[MODE] Bug @ {self.wpm} WPM")
        print("[INFO] Dit paddle = auto dits, Dah paddle = manual dah")
        print("[INFO] Press Ctrl+C to quit\n")
        
        dit_duration = 1200 / self.wpm
        element_space = dit_duration
        last_change_time = time.time()
        
        while self.running:
            dit_paddle, dah_paddle = self.read_key_state()
            
            # Dit paddle: automatic dits
            if dit_paddle:
                self.send_event(True, dit_duration)
                time.sleep(dit_duration / 1000.0)
                self.send_event(False, element_space)
                time.sleep(element_space / 1000.0)
            
            # Dah paddle: manual timing (like straight key)
            elif dah_paddle:
                if not self.last_key_down:
                    # Dah started
                    self.last_key_down = True
                    last_change_time = time.time()
            else:
                if self.last_key_down:
                    # Dah ended
                    current_time = time.time()
                    duration_ms = (current_time - last_change_time) * 1000.0
                    self.send_event(True, duration_ms)
                    time.sleep(duration_ms / 1000.0)
                    self.send_event(False, element_space)
                    time.sleep(element_space / 1000.0)
                    self.last_key_down = False
                else:
                    time.sleep(0.001)  # 1ms poll rate when idle
    
    def run(self):
        """Main run loop"""
        print("=" * 60)
        print("USB CW Key Sender - TCP Timestamp Protocol")
        print("=" * 60)
        
        # Connect to serial port
        if not self.connect_serial():
            return 1
        
        # Connect to receiver
        try:
            print(f"[TCP] Connecting to {self.host}:{self.port}...")
            self.protocol.connect(self.host, self.port)
            print(f"[TCP] Connected to {self.host}:{self.port}")
        except Exception as e:
            print(f"[ERROR] Could not connect: {e}")
            return 1
        
        self.running = True
        
        try:
            # Run appropriate mode
            if self.mode == 'straight':
                self.run_straight_key()
            elif self.mode in ['iambic-a', 'iambic-b']:
                self.run_iambic_keyer()
            elif self.mode == 'bug':
                self.run_bug()
            else:
                print(f"[ERROR] Unknown mode: {self.mode}")
                return 1
                
        except KeyboardInterrupt:
            print("\n\n[INFO] Interrupted by user")
        finally:
            self.cleanup()
        
        return 0
    
    def cleanup(self):
        """Cleanup resources"""
        print("\n[INFO] Cleaning up...")
        
        # Send final UP state
        if self.last_key_down:
            try:
                self.send_event(False, 100)
            except:
                pass
        
        # Close connections
        if self.sidetone:
            self.sidetone.close()
        
        if self.ser:
            self.ser.close()
        
        self.protocol.close()
        
        print("[INFO] Goodbye!")


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
        defaults['port'] = config.getint('network', 'port', fallback=7356)
    else:
        defaults['host'] = None
        defaults['port'] = 7356
    
    if config.has_section('keyer'):
        defaults['mode'] = config.get('keyer', 'mode', fallback='iambic-b')
        defaults['wpm'] = config.getint('keyer', 'wpm', fallback=20)
    else:
        defaults['mode'] = 'iambic-b'
        defaults['wpm'] = 20
    
    if config.has_section('serial'):
        defaults['serial_port'] = config.get('serial', 'port', fallback=None)
        if not defaults['serial_port']:  # Empty string in config
            defaults['serial_port'] = None
    else:
        defaults['serial_port'] = None
    
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
        description='USB CW Key Sender - TCP Timestamp Protocol',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using config file (no arguments needed if configured)
  python3 cw_usb_key_sender_tcp_ts.py
  
  # Straight key
  python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode straight
  
  # Iambic paddles (Mode B)
  python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode iambic-b --wpm 25
  
  # Bug (mechanical keyer)
  python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode bug --wpm 20

Config file locations (in order of precedence):
  1. ~/.cw_sender.ini (user home)
  2. ./cw_sender.ini (script directory)
        """
    )
    
    # Make host optional if it's in config
    if defaults['host']:
        parser.add_argument('host', nargs='?', default=defaults['host'],
                          help=f"Receiver IP address or hostname (default from config: {defaults['host']})")
    else:
        parser.add_argument('host', help='Receiver IP address or hostname')
    
    parser.add_argument('--port', type=int, default=defaults['port'],
                       help=f"TCP port (default: {defaults['port']} for timestamp protocol)")
    parser.add_argument('--mode', choices=['straight', 'iambic-a', 'iambic-b', 'bug'],
                       default=defaults['mode'],
                       help=f"Keyer mode (default: {defaults['mode']})")
    parser.add_argument('--wpm', type=int, default=defaults['wpm'],
                       help=f"Speed in WPM for iambic/bug modes (default: {defaults['wpm']})")
    parser.add_argument('--serial-port', default=defaults['serial_port'],
                       help='Serial port device (auto-detect if not specified)')
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
            print(f"  Port: {args.port}")
            print(f"  Mode: {args.mode}, WPM: {args.wpm}")
        print()
    
    sender = USBKeySender(
        host=args.host,
        port=args.port,
        mode=args.mode,
        wpm=args.wpm,
        serial_port=args.serial_port,
        no_audio=args.no_audio,
        debug=args.debug
    )
    
    return sender.run()


if __name__ == '__main__':
    sys.exit(main())
