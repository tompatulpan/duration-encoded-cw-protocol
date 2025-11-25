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

class IambicKeyer:
    """Iambic keyer logic (Mode A and Mode B)"""
    
    def __init__(self, wpm=20, mode='B'):
        self.mode = mode  # 'A' or 'B'
        self.wpm = wpm
        
        # Calculate timing
        self.dit_ms = 1200 / wpm
        self.dah_ms = self.dit_ms * 3
        self.element_space_ms = self.dit_ms
        
        # Keyer state
        self.last_element = None  # 'dit' or 'dah'
        self.dit_pending = False
        self.dah_pending = False
        
    def set_speed(self, wpm):
        """Change keyer speed"""
        self.wpm = wpm
        self.dit_ms = 1200 / wpm
        self.dah_ms = self.dit_ms * 3
        self.element_space_ms = self.dit_ms
    
    def update(self, dit_pressed, dah_pressed, send_callback):
        """
        Update keyer state and generate elements
        
        Args:
            dit_pressed: bool - dit paddle pressed
            dah_pressed: bool - dah paddle pressed
            send_callback: function(key_down, duration_ms) - called for each element
        
        Returns:
            bool - True if keyer is active (generating elements)
        """
        # Check for squeeze (both paddles)
        if dit_pressed and dah_pressed:
            # Start squeeze sequence
            if self.last_element == 'dah':
                # Send dit
                send_callback(True, self.dit_ms)
                time.sleep(self.dit_ms / 1000.0)
                send_callback(False, self.element_space_ms)
                time.sleep(self.element_space_ms / 1000.0)
                self.last_element = 'dit'
                
                # Mode B: remember dah was also pressed
                if self.mode == 'B':
                    self.dah_pending = True
            else:
                # Send dah (or start with dah if no last element)
                send_callback(True, self.dah_ms)
                time.sleep(self.dah_ms / 1000.0)
                send_callback(False, self.element_space_ms)
                time.sleep(self.element_space_ms / 1000.0)
                self.last_element = 'dah'
                
                # Mode B: remember dit was also pressed
                if self.mode == 'B':
                    self.dit_pending = True
            
            return True
        
        # Check for pending elements (Mode B only)
        if self.mode == 'B':
            if self.dit_pending and not dit_pressed:
                # Send pending dit
                send_callback(True, self.dit_ms)
                time.sleep(self.dit_ms / 1000.0)
                send_callback(False, self.element_space_ms)
                time.sleep(self.element_space_ms / 1000.0)
                self.last_element = 'dit'
                self.dit_pending = False
                return True
            
            if self.dah_pending and not dah_pressed:
                # Send pending dah
                send_callback(True, self.dah_ms)
                time.sleep(self.dah_ms / 1000.0)
                send_callback(False, self.element_space_ms)
                time.sleep(self.element_space_ms / 1000.0)
                self.last_element = 'dah'
                self.dah_pending = False
                return True
        
        # Single paddle
        if dit_pressed:
            send_callback(True, self.dit_ms)
            time.sleep(self.dit_ms / 1000.0)
            send_callback(False, self.element_space_ms)
            time.sleep(self.element_space_ms / 1000.0)
            self.last_element = 'dit'
            return True
        
        if dah_pressed:
            send_callback(True, self.dah_ms)
            time.sleep(self.dah_ms / 1000.0)
            send_callback(False, self.element_space_ms)
            time.sleep(self.element_space_ms / 1000.0)
            self.last_element = 'dah'
            return True
        
        # No activity - reset state
        if not dit_pressed and not dah_pressed:
            self.last_element = None
            self.dit_pending = False
            self.dah_pending = False
        
        return False


class USBKeySender:
    """Read CW key from USB serial port control lines"""
    
    def __init__(self, host='localhost', port=7355, serial_port='/dev/ttyUSB0', 
                 mode='straight', wpm=20, keyer_mode='B'):
        """
        Initialize USB key sender
        
        Args:
            host: Target host
            port: Target UDP port
            serial_port: Serial port device (e.g., /dev/ttyUSB0, COM3)
            mode: 'straight', 'bug', 'iambic' (iambic includes mode A/B)
            wpm: Speed in WPM (for keyer modes)
            keyer_mode: 'A' or 'B' for iambic keyer
        """
        self.protocol = CWProtocol()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host = host
        self.port = port
        self.mode = mode
        self.wpm = wpm
        
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
        
        print("=" * 60)
        print(f"USB CW Key Sender - {mode.upper()} mode")
        if mode == 'iambic':
            print(f"Iambic Mode {keyer_mode} - {wpm} WPM")
        print(f"Serial port: {serial_port}")
        print(f"Sending to {host}:{port}")
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
    
    def send_event(self, key_down, duration_ms):
        """Send a single CW event"""
        packet = self.protocol.create_packet(
            key_down=key_down,
            duration_ms=int(duration_ms)
        )
        self.sock.sendto(packet, (self.host, self.port))
        
        # Visual feedback
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
            
            time.sleep(0.002)  # 500 Hz polling
    
    def poll_iambic_keyer(self):
        """Poll iambic paddles and generate keyer output"""
        while self.running:
            # Read both paddles
            dit_pressed = self.serial.cts  # CTS = dit paddle
            dah_pressed = self.serial.dsr  # DSR = dah paddle
            
            # Update keyer logic
            active = self.keyer.update(dit_pressed, dah_pressed, self.send_event)
            
            if not active:
                # Small delay when idle
                time.sleep(0.005)  # 200 Hz when idle
    
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
        print("USB CW Key Sender")
        print("=" * 60)
        print("\nUsage:")
        print("  python3 cw_usb_key_sender.py <host> [mode] [wpm] [serial_port]")
        print("\nModes:")
        print("  straight    - Straight key (default)")
        print("  bug         - Semi-automatic bug")
        print("  iambic-a    - Iambic Mode A")
        print("  iambic-b    - Iambic Mode B (default for iambic)")
        print("\nExamples:")
        print("  python3 cw_usb_key_sender.py localhost")
        print("  python3 cw_usb_key_sender.py localhost iambic-b 25")
        print("  python3 cw_usb_key_sender.py 192.168.1.100 straight")
        print("  python3 cw_usb_key_sender.py localhost iambic-b 20 /dev/ttyUSB1")
        print()
        
        # List available ports
        list_serial_ports()
        return 1
    
    # Parse arguments
    host = sys.argv[1]
    mode_arg = sys.argv[2] if len(sys.argv) > 2 else 'straight'
    wpm = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    serial_port = sys.argv[4] if len(sys.argv) > 4 else None
    
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
        keyer_mode=keyer_mode
    )
    
    # Run
    sender.run()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
