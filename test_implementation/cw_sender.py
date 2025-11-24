#!/usr/bin/env python3
"""
CW Sender - Terminal-based CW key transmitter
Press and hold SPACE to key down, release to key up
"""

import socket
import sys
import time
import termios
import tty
import select
from cw_protocol import CWProtocol, UDP_PORT

class CWSender:
    def __init__(self, host='localhost', port=UDP_PORT):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.protocol = CWProtocol()
        
        self.key_down = False
        self.last_state_change = time.time()
        
        # Terminal settings
        self.old_settings = termios.tcgetattr(sys.stdin)
        
    def send_event(self, key_down):
        """Send key state change event"""
        current_time = time.time()
        duration_ms = (current_time - self.last_state_change) * 1000
        
        # Create and send packet
        packet = self.protocol.create_packet(key_down, duration_ms)
        self.socket.sendto(packet, (self.host, self.port))
        
        # Update state
        self.key_down = key_down
        self.last_state_change = current_time
        
        # Display feedback
        state_str = "KEY DOWN" if key_down else "KEY UP  "
        print(f"\r{state_str} | Duration: {duration_ms:6.1f}ms | Seq: {self.protocol.sequence_number-1:3d}",
              end='', flush=True)
    
    def run(self):
        """Main input loop"""
        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            
            print(f"CW Sender started - sending to {self.host}:{self.port}")
            print("Press and hold SPACE to key, release to un-key")
            print("Press Q to quit")
            print("-" * 60)
            
            space_pressed = False
            
            while True:
                # Check for key press (non-blocking)
                if select.select([sys.stdin], [], [], 0.01)[0]:
                    char = sys.stdin.read(1)
                    
                    if char.lower() == 'q':
                        # Send final key-up if needed
                        if self.key_down:
                            self.send_event(False)
                        print("\nQuitting...")
                        break
                    
                    elif char == ' ':
                        # Space pressed
                        if not space_pressed and not self.key_down:
                            space_pressed = True
                            self.send_event(True)
                
                # Check if space is still held (simple approach)
                # In reality, we can't easily detect key release in raw mode
                # So we use a different approach: toggle on each space press
                # Better implementation would use actual key up/down events
                
                # Sleep to avoid busy waiting
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            print("\nInterrupted")
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            
            # Send final key-up if needed
            if self.key_down:
                self.send_event(False)
            
            self.socket.close()


class CWSenderToggle(CWSender):
    """
    Alternative sender that toggles on each space press
    More practical for terminal testing
    """
    
    def run(self):
        """Main input loop with toggle mode"""
        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            
            print(f"CW Sender started - sending to {self.host}:{self.port}")
            print("Press SPACE to toggle key state")
            print("Press Q to quit")
            print("-" * 60)
            
            while True:
                # Wait for key press
                if select.select([sys.stdin], [], [], 0.01)[0]:
                    char = sys.stdin.read(1)
                    
                    if char.lower() == 'q':
                        # Send final key-up if needed
                        if self.key_down:
                            self.send_event(False)
                        print("\nQuitting...")
                        break
                    
                    elif char == ' ':
                        # Toggle key state
                        self.send_event(not self.key_down)
                
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            print("\nInterrupted")
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            
            # Send final key-up if needed
            if self.key_down:
                self.send_event(False)
            
            self.socket.close()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = 'localhost'
    
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    else:
        port = UDP_PORT
    
    print("Mode: Toggle (press SPACE to toggle key state)")
    print("For true key-down/key-up, use a GPIO device\n")
    
    sender = CWSenderToggle(host, port)
    sender.run()
