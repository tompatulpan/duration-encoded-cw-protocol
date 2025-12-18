#!/usr/bin/env python3
"""
CW XIAO Sender with TCP Timestamps

Reads XIAO SAMD21/RP2040 USB HID device and sends TCP+TS packets.
Uses shared xiao_hid_reader module for HID communication.

For LAN/direct connections to receiver.

Usage:
    python3 cw_xiao_sender_tcp_ts.py <receiver_ip> --mode straight
    python3 cw_xiao_sender_tcp_ts.py <receiver_ip> --mode iambic-b --wpm 25
"""

import sys
import os
import time
import argparse

# Add test_implementation directory to Python path
sys.path.insert(0, '../test_implementation')

from xiao_hid_reader import XiaoHIDReader
from cw_protocol_tcp_ts import CWProtocolTCPTimestamp
from cw_receiver import SidetoneGenerator


class IambicKeyer:
    """Iambic keyer logic (Mode A and Mode B) - aligned with cw_xiao_hidraw_sender.py"""
    
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
    
    def update(self, paddle_reader, send_element_callback):
        """
        Main keyer update - call this in a loop
        
        Args:
            paddle_reader: function() -> (dit: bool, dah: bool) - reads current paddle states
            send_element_callback: function(key_down: bool, duration_ms: float)
        
        Returns:
            bool - True if keyer is active, False if idle
        """
        
        # Read current paddle states
        dit_paddle, dah_paddle = paddle_reader()
        
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
                # READ FRESH paddle state!
                dit_paddle, dah_paddle = paddle_reader()
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
                # READ FRESH paddle state!
                dit_paddle, dah_paddle = paddle_reader()
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                return False  # Still idle
                
        # State: DIT - just sent a dit
        elif self.state == self.DIT:
            # Sample paddles during element space - READ FRESH!
            dit_paddle, dah_paddle = paddle_reader()
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
                
                # Mode B: Check for dit during dah - READ FRESH!
                dit_paddle, dah_paddle = paddle_reader()
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
                
                # Mode B: Check for dah during dit - READ FRESH!
                dit_paddle, dah_paddle = paddle_reader()
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
            else:
                # No memory, return to idle
                self.state = self.IDLE
                return False
                
        # State: DAH - just sent a dah
        elif self.state == self.DAH:
            # Sample paddles during element space - READ FRESH!
            dit_paddle, dah_paddle = paddle_reader()
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
                
                # Mode B: Check for dah during dit - READ FRESH!
                dit_paddle, dah_paddle = paddle_reader()
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
                
                # Mode B: Check for dit during dah - READ FRESH!
                dit_paddle, dah_paddle = paddle_reader()
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                # No memory, return to idle
                self.state = self.IDLE
                return False
        
        return True  # Keyer is active


def main():
    parser = argparse.ArgumentParser(
        description="XIAO CW Sender (TCP+TS Protocol)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Straight key:
    python3 cw_xiao_sender_tcp_ts.py 192.168.1.100 --mode straight
    
  Iambic Mode B paddle:
    python3 cw_xiao_sender_tcp_ts.py 192.168.1.100 --mode iambic-b --wpm 25
    
  With debug output:
    python3 cw_xiao_sender_tcp_ts.py localhost --mode straight --debug
        """
    )
    
    parser.add_argument('host', help='Receiver IP address')
    parser.add_argument('--port', type=int, default=7356, help='Receiver port (default: 7356)')
    parser.add_argument('--mode', choices=['straight', 'iambic-a', 'iambic-b'], 
                       default='iambic-b', help='Keying mode (default: iambic-b)')
    parser.add_argument('--wpm', type=int, default=20, help='Keyer speed in WPM (default: 20)')
    parser.add_argument('--device', help='Explicit /dev/hidraw* device path')
    parser.add_argument('--no-sidetone', action='store_true', help='Disable sidetone audio')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Print header
    print("=" * 70)
    print("CW XIAO Sender with TCP Timestamps")
    print("=" * 70)
    print(f"Mode: {args.mode.upper()}")
    print(f"Receiver: {args.host}:{args.port}")
    print("-" * 70)
    
    # Initialize HID reader
    hid_reader = XiaoHIDReader(device_path=args.device, debug=args.debug)
    if not hid_reader.connect():
        return 1
    
    # Initialize sidetone
    sidetone = None
    if not args.no_sidetone:
        try:
            sidetone = SidetoneGenerator(frequency=600)  # TX frequency
            print("Sidetone: 600 Hz")
        except Exception as e:
            print(f"Warning: Could not initialize sidetone: {e}")
    
    # Initialize iambic keyer if needed
    keyer = None
    if args.mode in ['iambic-a', 'iambic-b']:
        keyer_mode_letter = 'B' if args.mode == 'iambic-b' else 'A'
        keyer = IambicKeyer(args.wpm, mode=keyer_mode_letter)
        print(f"Keyer: Iambic Mode {keyer_mode_letter}, {args.wpm} WPM")
    
    # Connect to receiver with retry logic
    max_retries = 10
    retry_delay = 2.0
    connect_timeout = 3.0  # Socket timeout for quick retry
    protocol = None
    
    for attempt in range(max_retries):
        try:
            protocol = CWProtocolTCPTimestamp()
            protocol.connect(args.host, args.port, timeout=connect_timeout)
            print(f"Connected to {args.host}:{args.port}")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Connection attempt {attempt + 1}/{max_retries} failed: {e}")
                print(f"Retrying in {retry_delay} seconds... (waiting for receiver)")
                time.sleep(retry_delay)
            else:
                print(f"\nError: Could not connect after {max_retries} attempts")
                print(f"Make sure receiver is running: python3 cw_receiver_tcp_ts.py")
                hid_reader.close()
                if sidetone:
                    sidetone.close()
                return 1
    
    # Helper function to send with auto-reconnect on connection loss
    def send_packet_with_reconnect(key_down_state, duration_ms):
        """Send packet with automatic reconnection on failure"""
        nonlocal protocol
        
        # First, try to send
        try:
            protocol.send_packet(key_down_state, duration_ms)
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"\n[TCP] Connection lost: {e}")
            print(f"[TCP] Attempting to reconnect...")
            
            # Try to reconnect with multiple attempts
            max_reconnect_attempts = 5
            reconnect_delay = 2.0
            
            for attempt in range(max_reconnect_attempts):
                try:
                    protocol.close()
                    time.sleep(reconnect_delay)
                    protocol = CWProtocolTCPTimestamp()
                    protocol.connect(args.host, args.port, timeout=connect_timeout)
                    print(f"[TCP] ✓ Reconnected to {args.host}:{args.port}")
                    
                    # Try to send the packet again after successful reconnection
                    try:
                        protocol.send_packet(key_down_state, duration_ms)
                        return True
                    except Exception as send_err:
                        print(f"[TCP] Send after reconnection failed: {send_err}")
                        continue  # Try reconnecting again
                        
                except Exception as reconnect_err:
                    if attempt < max_reconnect_attempts - 1:
                        print(f"[TCP] Reconnection attempt {attempt + 1}/{max_reconnect_attempts} failed, retrying...")
                    else:
                        print(f"[TCP] ✗ Could not reconnect after {max_reconnect_attempts} attempts")
                        print(f"[TCP] Continuing without connection (packets will be dropped)")
                        return False
            
            return False
    
    print("\nReady to transmit (Ctrl+C to exit)")
    if args.debug:
        print("Debug mode: Showing HID data and state changes")
    print("-" * 70)
    
    # State tracking
    key_down = False
    transmission_start = None
    last_event_time = time.time()
    loop_count = 0
    
    # Helper function to read current paddle states (used by iambic keyer)
    def read_paddle_states():
        """Read current paddle states - called by keyer during elements"""
        return hid_reader.read_paddles()
    
    # Helper function for keyer to send events
    def send_element(key_down_state, duration_ms):
        """Send a CW element (used by iambic keyer)
        
        Args:
            key_down_state: True for DOWN, False for UP
            duration_ms: Element duration (dit/dah length or spacing)
        """
        nonlocal last_event_time, transmission_start
        
        now = time.time()
        
        # Calculate duration of PREVIOUS state (protocol semantics)
        if transmission_start is None:
            transmission_start = now
            previous_duration_ms = 0
        else:
            previous_duration_ms = int((now - last_event_time) * 1000)
        
        # Cap duration to prevent overflow
        previous_duration_ms = min(previous_duration_ms, 65535)
        
        # Send packet with PREVIOUS state's duration
        if not send_packet_with_reconnect(key_down_state, previous_duration_ms):
            raise ConnectionError("Failed to send packet after reconnection attempts")
        
        # Update sidetone
        if sidetone:
            sidetone.set_key(key_down_state)
        
        # Debug output - show what we SENT in packet (previous state duration)
        state_str = "DOWN" if key_down_state else "UP"
        if args.debug:
            timestamp_ms = int((now - transmission_start) * 1000)
            print(f"[SEND] {state_str} {previous_duration_ms:5d}ms (ts={timestamp_ms}ms)")
        else:
            print(f"[KEY] {state_str:4s} {previous_duration_ms:5d}ms")
        
        last_event_time = now
    
    try:
        while True:
            loop_count += 1
            
            # Show heartbeat every 5000 loops when in debug mode
            if args.debug and loop_count % 5000 == 0:
                print(f"[LOOP] Iteration {loop_count}, reads: {hid_reader.read_count}")
            
            # Iambic mode - use keyer logic
            if keyer:
                keyer.update(read_paddle_states, send_element)
                time.sleep(0.001)  # 1ms polling
            
            # Straight key mode
            else:
                dit, dah = hid_reader.read_paddles()
                new_key_down = dit or dah
                
                # Detect state change
                if new_key_down != key_down:
                    now = time.time()
                    
                    # Calculate duration of previous state
                    if transmission_start is None:
                        transmission_start = now
                        duration_ms = 0
                    else:
                        duration_ms = int((now - last_event_time) * 1000)
                        duration_ms = min(duration_ms, 65535)
                    
                    # Send event
                    if not send_packet_with_reconnect(new_key_down, duration_ms):
                        print("\n[ERROR] Connection lost and could not reconnect. Exiting.")
                        break
                    
                    # Update state
                    key_down = new_key_down
                    last_event_time = now
                    
                    # Update sidetone
                    if sidetone:
                        sidetone.set_key(key_down)
                    
                    # Debug output
                    state_str = "DOWN" if key_down else "UP"
                    if args.debug:
                        timestamp_ms = int((now - transmission_start) * 1000)
                        print(f"[SEND] {state_str} {duration_ms:5d}ms (ts={timestamp_ms}ms)")
                    else:
                        print(f"[KEY] {state_str:4s} {duration_ms:5d}ms")
                
                time.sleep(0.001)  # 1ms polling
    
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    
    finally:
        # Send final UP event if key was down
        if key_down and last_event_time:
            duration_ms = int((time.time() - last_event_time) * 1000)
            duration_ms = min(duration_ms, 65535)
            send_packet_with_reconnect(False, duration_ms)
        
        # Send EOT
        protocol.send_eot_packet()
        time.sleep(0.1)
        
        # Cleanup
        hid_reader.close()
        protocol.close()
        if sidetone:
            sidetone.close()
        
        print("Disconnected")
    
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nShutdown requested (Ctrl+C)")
        sys.exit(0)
