#!/usr/bin/env python3
"""
CW XIAO HID Key Sender with TCP Timestamps (Raw hidraw access)

Reads XIAO SAMD21 USB HID device using raw hidraw and sends TCP-TS packets.
Uses direct /dev/hidraw* access instead of hidapi library.

Usage: python3 cw_xiao_hidraw_sender.py <receiver_ip> --mode straight
"""

import sys
import os
import time
import argparse
import glob
import struct

# Add test_implementation directory to Python path to import protocol modules
# This allows USB_HID folder to use the shared protocol implementations
# without duplicating code. The path is relative: ../test_implementation
sys.path.insert(0, '../test_implementation')
from cw_protocol_tcp_ts import CWProtocolTCPTimestamp
from cw_receiver import SidetoneGenerator

# XIAO SAMD21 USB IDs
XIAO_VID = "2886"
XIAO_PID = "802f"


class IambicKeyer:
    """Iambic keyer logic (Mode A and Mode B) - same as UDP-TS version"""
    
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

class XIAOHIDRawKey:
    def __init__(self, vid=XIAO_VID, pid=XIAO_PID, device_path=None, debug=False):
        self.device_fd = None
        self.device_path = device_path  # Can be specified manually
        self.vid = vid
        self.pid = pid
        self.last_dit = False
        self.last_dah = False
        self.debug = debug
        self.read_count = 0

    def get_device_ids(self, hidraw_path):
        """Get VID/PID from sysfs for a hidraw device"""
        try:
            hidraw_name = os.path.basename(hidraw_path)
            sysfs_base = f'/sys/class/hidraw/{hidraw_name}/device'
            
            # Try reading from uevent file
            uevent_path = f'{sysfs_base}/uevent'
            if os.path.exists(uevent_path):
                with open(uevent_path, 'r') as f:
                    content = f.read()
                    vid = None
                    pid = None
                    for line in content.split('\n'):
                        if line.startswith('HID_ID='):
                            # Format: HID_ID=0003:00002886:0000802F
                            parts = line.split('=')
                            if len(parts) == 2:
                                ids = parts[1].split(':')
                                if len(ids) == 3:
                                    vid = ids[1].lstrip('0').lower()
                                    pid = ids[2].lstrip('0').lower()
                                    return (vid, pid)
        except Exception:
            pass
        return (None, None)
    
    def find_device(self):
        """Find the hidraw device matching VID:PID"""
        for hidraw_path in glob.glob('/dev/hidraw*'):
            try:
                # Try sysfs first (more reliable)
                vid, pid = self.get_device_ids(hidraw_path)
                if vid and pid:
                    if vid == self.vid.lower() and pid == self.pid.lower():
                        return hidraw_path
                
                # Fallback to udevadm
                import subprocess
                result = subprocess.run(
                    ['udevadm', 'info', hidraw_path],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    output = result.stdout
                    if f'ID_VENDOR_ID={self.vid}' in output and f'ID_MODEL_ID={self.pid}' in output:
                        return hidraw_path
            except Exception:
                continue
        return None

    def connect(self):
        try:
            # Find the device (if not manually specified)
            if not self.device_path:
                self.device_path = self.find_device()
            
            if not self.device_path:
                print(f"Error: XIAO device not found (VID:PID {self.vid}:{self.pid})")
                print("\nAvailable hidraw devices:")
                for hidraw_path in glob.glob('/dev/hidraw*'):
                    vid, pid = self.get_device_ids(hidraw_path)
                    print(f"  {hidraw_path}")
                    if vid and pid:
                        print(f"    VID:PID = {vid}:{pid}")
                        if vid == self.vid.lower() and pid == self.pid.lower():
                            print(f"    *** This is the XIAO! Use: --device {hidraw_path}")
                    else:
                        # Try udevadm as fallback
                        try:
                            import subprocess
                            result = subprocess.run(
                                ['udevadm', 'info', hidraw_path],
                                capture_output=True,
                                text=True,
                                timeout=1
                            )
                            if result.returncode == 0:
                                for line in result.stdout.split('\n'):
                                    if 'ID_VENDOR_ID' in line or 'ID_MODEL_ID' in line or 'ID_SERIAL' in line:
                                        print(f"    {line.split('=')[1] if '=' in line else line}")
                        except Exception:
                            print("    (no device info available)")
                    print()
                print("\nTip: Use --device /dev/hidrawX to specify device manually")
                return False

            print(f"Found XIAO at: {self.device_path}")

            # Open device with raw file operations
            self.device_fd = os.open(self.device_path, os.O_RDWR | os.O_NONBLOCK)
            
            print(f"Connected: XIAO SAMD21 (raw hidraw)")
            print(f"Device: {self.device_path}")
            print(f"VID:PID: {self.vid}:{self.pid}\n")
            return True

        except PermissionError:
            print(f"Error: Permission denied accessing {self.device_path}")
            print("\nTry one of these fixes:")
            print("1. Add udev rule (recommended):")
            print('   echo \'KERNEL=="hidraw*", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="802f", MODE="0666", TAG+="uaccess"\' | sudo tee /etc/udev/rules.d/99-xiao.rules')
            print("   sudo udevadm control --reload-rules")
            print("   sudo udevadm trigger")
            print("\n2. Run with sudo (not recommended for permanent use):")
            print(f"   sudo {' '.join(sys.argv)}")
            return False

        except Exception as e:
            print(f"Error connecting: {e}")
            return False

    def read_paddles(self):
        """Read paddle state from HID device"""
        if self.device_fd is None:
            return None
        try:
            # Read up to 64 bytes (typical HID report size)
            data = os.read(self.device_fd, 64)
            if data and len(data) > 0:
                self.read_count += 1
                
                # Debug: Show ALL reads when debugging
                if self.debug and self.read_count <= 10:
                    print(f"[HID READ #{self.read_count}] Received {len(data)} bytes: {data.hex()}")
                
                # HID report format: [report_id, button_data, ...]
                # XIAO firmware sends report ID 1, but Linux may present it differently
                report_id = data[0]
                
                if len(data) >= 2 and report_id in (0x01, 0x02):  # Accept report ID 1 or 2
                    buttons = data[1]  # Modifier byte (keyboard HID report format)
                elif len(data) >= 1:
                    # Fallback: assume no report ID (modifier byte at index 0)
                    buttons = data[0]
                else:
                    # No data
                    return (self.last_dit, self.last_dah)
                
                # USB HID keyboard modifier bits (XIAO uses Keyboard library)
                # Bit 0 (0x01) = Left Ctrl  -> Dit paddle
                # Bit 4 (0x10) = Right Ctrl -> Dah paddle
                dit = bool(buttons & 0x01)  # Left Ctrl
                dah = bool(buttons & 0x10)  # Right Ctrl (NOT 0x02!)
                
                # Debug: Show button state changes
                if self.debug and (dit != self.last_dit or dah != self.last_dah):
                    print(f"[BUTTON CHANGE] Buttons: 0x{buttons:02x} | Dit: {dit}, Dah: {dah}")
                
                self.last_dit = dit
                self.last_dah = dah
                return (dit, dah)
            return (self.last_dit, self.last_dah)
        except BlockingIOError:
            # No data available (non-blocking read)
            return (self.last_dit, self.last_dah)
        except Exception as e:
            print(f"Read error: {e}")
            return None

    def close(self):
        if self.device_fd is not None:
            os.close(self.device_fd)
            self.device_fd = None

def main():
    parser = argparse.ArgumentParser(description='CW XIAO HID Sender (TCP-TS, raw hidraw)')
    parser.add_argument('host', help='Receiver IP address')
    parser.add_argument('--port', type=int, default=7356, help='TCP port')
    parser.add_argument('--device', help='Specify hidraw device manually (e.g., /dev/hidraw2)')
    parser.add_argument('--mode', choices=['straight', 'iambic-a', 'iambic-b'], default='iambic-b',
                        help='Keyer mode (default: iambic-b)')
    parser.add_argument('--wpm', type=int, default=20, help='Keyer speed in WPM (default: 20)')
    parser.add_argument('--no-sidetone', action='store_true')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    print("=" * 70)
    print("CW XIAO HID Key Sender with TCP Timestamps (Raw hidraw)")
    print("=" * 70)
    print(f"Mode: {args.mode.upper()}")
    if args.mode in ['iambic-a', 'iambic-b']:
        print(f"Speed: {args.wpm} WPM")
    print(f"Receiver: {args.host}:{args.port}")
    if args.device:
        print(f"Device: {args.device} (manual)")
    print("-" * 70)
    print()

    # Connect to XIAO
    hid_key = XIAOHIDRawKey(device_path=args.device, debug=args.debug)
    if not hid_key.connect():
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

    # Connect to receiver
    try:
        protocol = CWProtocolTCPTimestamp()
        protocol.connect(args.host, args.port)
        print(f"Connected to {args.host}:{args.port}")
    except Exception as e:
        print(f"Error connecting to receiver: {e}")
        hid_key.close()
        return 1

    print("\nReady to transmit (Ctrl+C to exit)")
    if args.debug:
        print("Debug mode: Showing HID data and state changes")
    print("-" * 70)

    key_down = False
    transmission_start = None
    loop_count = 0
    last_event_time = time.time()
        # Helper function to read current paddle states (used by iambic keyer)
    def read_paddle_states():
        """Read current paddle states - called by keyer during elements"""
        paddles = hid_key.read_paddles()
        if paddles is None:
            return (False, False)  # Connection lost
        return paddles
        # Helper function for keyer to send events
    def send_element(key_down_state, duration_ms):
        """Send a CW element (used by iambic keyer)
        
        Note: duration_ms is the duration to KEY this element (dit/dah length),
        but protocol expects duration of PREVIOUS state. We'll calculate that.
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
        
        # Calculate timestamp
        timestamp_ms = int((now - transmission_start) * 1000)
        
        # Send packet with PREVIOUS state's duration
        protocol.send_packet(key_down_state, previous_duration_ms)
        
        # Update sidetone
        if sidetone:
            sidetone.set_key(key_down_state)
        
        # Debug output matching TCP-TS version
        state_str = "DOWN" if key_down_state else "UP"
        if args.debug:
            print(f"[SEND] {state_str} {previous_duration_ms:5d}ms (ts={timestamp_ms}ms)")
        else:
            print(f"[KEY] {state_str:4s} {previous_duration_ms:5d}ms")
        
        last_event_time = now

    try:
        while True:
            loop_count += 1
            
            # Show heartbeat every 5000 loops when in debug mode
            if args.debug and loop_count % 5000 == 0:
                print(f"[LOOP] Iteration {loop_count}, reads: {hid_key.read_count}, last state: dit={hid_key.last_dit}, dah={hid_key.last_dah}")
            
            paddles = hid_key.read_paddles()
            if paddles is None:
                print("Lost connection to XIAO")
                break

            dit, dah = paddles
            
            # Iambic mode - use keyer logic with paddle reader callback
            if keyer:
                # Let keyer handle timing and event sending
                # Pass paddle reader callback so keyer can read fresh states during elements
                keyer.update(read_paddle_states, send_element)
                time.sleep(0.001)  # 1ms polling
                
            # Straight key mode
            else:
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
                        # Cap duration to prevent overflow (65535ms = 65.5 seconds)
                        duration_ms = min(duration_ms, 65535)
                    
                    # Calculate timestamp
                    timestamp_ms = int((now - transmission_start) * 1000)

                    # Send event
                    protocol.send_packet(new_key_down, duration_ms)

                    # Update state
                    key_down = new_key_down
                    last_event_time = now

                    # Update sidetone
                    if sidetone:
                        sidetone.set_key(key_down)

                    # Debug output matching TCP-TS version
                    state_str = "DOWN" if key_down else "UP"
                    if args.debug:
                        print(f"[SEND] {state_str} {duration_ms:5d}ms (ts={timestamp_ms}ms)")
                    else:
                        print(f"[KEY] {state_str:4s} {duration_ms:5d}ms")

                time.sleep(0.001)  # 1ms polling (same as USB HID)

    except KeyboardInterrupt:
        print("\n\nShutting down...")

    finally:
        # Send final UP event if key was down
        if key_down and last_event_time:
            duration_ms = int((time.time() - last_event_time) * 1000)
            duration_ms = min(duration_ms, 65535)
            protocol.send_packet(False, duration_ms)

        # Send EOT
        protocol.send_eot_packet()
        time.sleep(0.1)  # Give receiver time to process

        # Cleanup
        hid_key.close()
        protocol.close()
        if sidetone:
            sidetone.close()

        print("Disconnected")

    return 0

if __name__ == '__main__':
    sys.exit(main())
