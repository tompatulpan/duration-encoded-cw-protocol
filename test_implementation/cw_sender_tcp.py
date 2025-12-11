#!/usr/bin/env python3
"""
CW Sender TCP - Terminal-based CW key transmitter over TCP
Press and hold SPACE to key down, release to key up
"""

import sys
import time
import termios
import tty
import select
from cw_protocol_tcp import CWProtocolTCP, TCP_PORT


class CWSenderTCP:
    def __init__(self, host='localhost', port=TCP_PORT):
        self.host = host
        self.port = port
        self.protocol = CWProtocolTCP()
        
        self.key_down = False
        self.last_state_change = time.time()
        
        # Terminal settings
        self.old_settings = termios.tcgetattr(sys.stdin)
        
        # Connection state
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        
    def connect(self):
        """Establish connection to receiver"""
        print(f"[TCP] Connecting to {self.host}:{self.port}...", end='', flush=True)
        
        if self.protocol.connect(self.host, self.port, timeout=5.0):
            print(" connected!")
            self.connected = True
            self.reconnect_attempts = 0
            return True
        else:
            print(" failed!")
            self.connected = False
            return False
    
    def reconnect(self):
        """Attempt to reconnect to receiver"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"\n[TCP] Max reconnection attempts ({self.max_reconnect_attempts}) reached")
            return False
        
        self.reconnect_attempts += 1
        print(f"\n[TCP] Reconnecting... (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
        time.sleep(1.0)  # Wait before retry
        
        return self.connect()
    
    def send_event(self, key_down):
        """Send key state change event"""
        if not self.connected:
            print("\r[ERROR] Not connected - cannot send event", end='', flush=True)
            return False
        
        current_time = time.time()
        duration_ms = (current_time - self.last_state_change) * 1000
        
        # Send packet
        if not self.protocol.send_packet(key_down, duration_ms):
            print("\r[ERROR] Send failed - connection lost", end='', flush=True)
            self.connected = False
            return False
        
        # Update state
        self.key_down = key_down
        self.last_state_change = current_time
        
        # Display feedback
        state_str = "KEY DOWN" if key_down else "KEY UP  "
        seq = self.protocol.sequence_number - 1
        print(f"\r{state_str} | Duration: {duration_ms:6.1f}ms | Seq: {seq:3d} | TCP Connected",
              end='', flush=True)
        
        return True
    
    def cleanup(self):
        """Send final key-up and close connection"""
        # Restore terminal
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
        
        # Send final key-up if needed
        if self.key_down and self.connected:
            print("\n[TCP] Sending final key-up...")
            self.send_event(False)
        
        # Send EOT packet
        if self.connected:
            print("[TCP] Sending End-of-Transmission...")
            self.protocol.send_eot_packet()
        
        # Close connection
        self.protocol.close()
        print("[TCP] Connection closed")
    
    def run(self):
        """Main input loop"""
        # Connect to receiver
        if not self.connect():
            print("Failed to connect to receiver")
            return
        
        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            
            print(f"CW Sender TCP started - connected to {self.host}:{self.port}")
            print("Press and hold SPACE to key, release to un-key")
            print("Press Q to quit")
            print("-" * 60)
            
            space_pressed = False
            
            while True:
                # Check connection status
                if not self.connected:
                    # Try to reconnect
                    if not self.reconnect():
                        print("\nConnection lost and reconnection failed - exiting")
                        break
                    # Reset state after reconnection
                    self.last_state_change = time.time()
                    self.key_down = False
                
                # Check for key press (non-blocking)
                if select.select([sys.stdin], [], [], 0.01)[0]:
                    char = sys.stdin.read(1)
                    
                    if char.lower() == 'q':
                        print("\nQuitting...")
                        break
                    
                    elif char == ' ':
                        # Space pressed - toggle key state
                        if not space_pressed and not self.key_down:
                            space_pressed = True
                            if not self.send_event(True):
                                # Send failed, will try to reconnect on next loop
                                pass
                
                # Sleep to avoid busy waiting
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            print("\nInterrupted")
        finally:
            self.cleanup()


class CWSenderToggleTCP(CWSenderTCP):
    """
    Alternative sender that toggles on each space press
    More practical for terminal testing
    """
    
    def run(self):
        """Main input loop with toggle mode"""
        # Connect to receiver
        if not self.connect():
            print("Failed to connect to receiver")
            return
        
        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            
            print(f"CW Sender TCP started - connected to {self.host}:{self.port}")
            print("Press SPACE to toggle key state")
            print("Press Q to quit")
            print("-" * 60)
            
            while True:
                # Check connection status
                if not self.connected:
                    # Try to reconnect
                    if not self.reconnect():
                        print("\nConnection lost and reconnection failed - exiting")
                        break
                    # Reset state after reconnection
                    self.last_state_change = time.time()
                    self.key_down = False
                
                # Wait for key press
                if select.select([sys.stdin], [], [], 0.01)[0]:
                    char = sys.stdin.read(1)
                    
                    if char.lower() == 'q':
                        print("\nQuitting...")
                        break
                    
                    elif char == ' ':
                        # Toggle key state
                        if not self.send_event(not self.key_down):
                            # Send failed, will try to reconnect on next loop
                            pass
                
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            print("\nInterrupted")
        finally:
            self.cleanup()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = 'localhost'
    
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    else:
        port = TCP_PORT
    
    print("=" * 60)
    print("CW Sender - TCP Version")
    print("=" * 60)
    print("Mode: Toggle (press SPACE to toggle key state)")
    print("For true key-down/key-up, use a GPIO device\n")
    
    sender = CWSenderToggleTCP(host, port)
    sender.run()
