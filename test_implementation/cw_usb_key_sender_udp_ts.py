#!/usr/bin/env python3
"""
CW USB Key Sender UDP with Timestamps
Physical key input via USB serial adapter, transmit over UDP with timestamps
"""

import argparse
import time
import serial
from cw_protocol_udp_ts import CWProtocolUDPTimestamp, UDP_TS_PORT
from cw_receiver import SidetoneGenerator


class IambicKeyer:
    """Iambic keyer logic (Mode A and Mode B) - same as TCP-TS version"""
    
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
        
        return True  # Keyer is active


class USBKeySenderUDPTimestamp:
    """USB key sender with UDP timestamp protocol"""
    
    def __init__(self, host, port, serial_port, wpm, keyer_mode, sidetone_enabled=True, debug=False):
        self.host = host
        self.port = port
        self.serial_port = serial_port
        self.wpm = wpm
        self.keyer_mode = keyer_mode
        self.sidetone_enabled = sidetone_enabled
        self.debug = debug
        
        # Protocol
        self.protocol = CWProtocolUDPTimestamp()
        self.dest_addr = (host, port)
        
        # Serial port
        self.ser = None
        
        # Sidetone (TX frequency)
        self.sidetone = None
        if sidetone_enabled:
            self.sidetone = SidetoneGenerator(frequency=600)
        
        # Keyer logic
        self.keyer = None
        if keyer_mode in ['iambic-a', 'iambic-b']:
            keyer_mode_letter = 'B' if keyer_mode == 'iambic-b' else 'A'
            self.keyer = IambicKeyer(wpm, mode=keyer_mode_letter)
        
        # State tracking
        self.last_dit = False
        self.last_dah = False
        self.current_key_state = False
    
    def send_event(self, key_down, duration_ms):
        """Send CW event (timing handled by keyer)"""
        # Convert to int if needed
        duration_ms = int(duration_ms)
        
        # Send packet
        self.protocol.send_packet(key_down, duration_ms, self.dest_addr)
        
        # Control sidetone
        if self.sidetone:
            self.sidetone.set_key(key_down)
        
        # Update state
        self.current_key_state = key_down
        
        # Note: No sleep here - keyer handles timing!
        
        if self.debug:
            state_str = "DOWN" if key_down else "UP"
            print(f"[SEND] {state_str} {duration_ms}ms")
    
    def run(self):
        """Main sender loop"""
        print(f"CW USB Key Sender UDP Timestamp")
        print(f"Destination: {self.host}:{self.port}")
        print(f"Serial port: {self.serial_port}")
        print(f"Speed: {self.wpm} WPM")
        print(f"Mode: {self.keyer_mode}")
        print(f"Serial pins: Dit = CTS, Dah = DSR")
        print("="*50)
        
        # Open serial port
        try:
            self.ser = serial.Serial(self.serial_port, baudrate=9600, timeout=0.01)
            print(f"Serial port opened: {self.serial_port}")
        except Exception as e:
            print(f"[ERROR] Failed to open serial port: {e}")
            return
        
        # Display initial pin states for debugging
        time.sleep(0.1)
        print(f"\nInitial pin states:")
        print(f"  CTS (dit): {self.ser.cts}")
        print(f"  DSR (dah): {self.ser.dsr}")
        print(f"  CD:        {self.ser.cd}")
        
        if self.ser.cts:
            print("[WARNING] CTS is HIGH - check wiring (should be LOW when not pressed)")
        if self.ser.dsr:
            print("[WARNING] DSR is HIGH - check wiring (should be LOW when not pressed)")
        
        print("\nReady to send CW! (Ctrl+C to exit)")
        print("="*50)
        
        # Create socket
        self.protocol.sock = self.protocol.create_socket(0)  # Use ephemeral port
        
        try:
            while True:
                # Read paddle states
                dit_pressed = self.ser.cts  # CTS = dit paddle
                dah_pressed = self.ser.dsr  # DSR = dah paddle
                
                # Process based on mode
                if self.keyer_mode == 'straight':
                    # Straight key: Dit paddle only, immediate on/off
                    if dit_pressed != self.last_dit:
                        if dit_pressed:
                            # Key down - don't know duration yet
                            self.send_event(True, 1)  # Minimal duration
                        else:
                            # Key up - send previous down duration
                            # (In straight key mode, timing is handled externally)
                            self.send_event(False, 1)
                        self.last_dit = dit_pressed
                
                elif self.keyer_mode == 'bug':
                    # Bug mode: Dit paddle = automatic dots, Dah paddle = manual dash
                    # Dit paddle (automatic)
                    if dit_pressed and not self.last_dit:
                        dit_ms = int(1200 / self.wpm)
                        self.send_event(True, dit_ms)
                        self.send_event(False, dit_ms)
                    
                    # Dah paddle (manual)
                    if dah_pressed != self.last_dah:
                        if dah_pressed:
                            self.send_event(True, 1)
                        else:
                            self.send_event(False, 1)
                    
                    self.last_dit = dit_pressed
                    self.last_dah = dah_pressed
                
                elif self.keyer_mode in ['iambic-a', 'iambic-b']:
                    # Iambic keyer (blocking, polls paddles internally)
                    self.keyer.update(dit_pressed, dah_pressed, self.send_event)
                
                # Small sleep to avoid busy-waiting
                time.sleep(0.001)  # 1ms polling
        
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        
        finally:
            # Turn off key if it's on
            if self.current_key_state:
                self.send_event(False, 1)
            
            # Cleanup
            if self.sidetone:
                self.sidetone.close()
            
            if self.ser:
                self.ser.close()
            
            if self.protocol.sock:
                self.protocol.close()
            
            print("Sender stopped.")


def main():
    parser = argparse.ArgumentParser(description='CW USB Key Sender UDP with Timestamps')
    parser.add_argument('host', help='Receiver hostname or IP address')
    parser.add_argument('--port', type=int, default=UDP_TS_PORT,
                       help=f'UDP port (default: {UDP_TS_PORT})')
    parser.add_argument('--serial-port', default='/dev/ttyUSB0',
                       help='Serial port device (default: /dev/ttyUSB0)')
    parser.add_argument('--wpm', type=int, default=25,
                       help='Words per minute for iambic keyer (default: 25)')
    parser.add_argument('--mode', choices=['straight', 'bug', 'iambic-a', 'iambic-b'],
                       default='iambic-b',
                       help='Keyer mode (default: iambic-b)')
    parser.add_argument('--no-sidetone', action='store_true',
                       help='Disable sidetone audio')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug output')
    
    args = parser.parse_args()
    
    sender = USBKeySenderUDPTimestamp(
        host=args.host,
        port=args.port,
        serial_port=args.serial_port,
        wpm=args.wpm,
        keyer_mode=args.mode,
        sidetone_enabled=not args.no_sidetone,
        debug=args.debug
    )
    
    sender.run()


if __name__ == '__main__':
    main()
