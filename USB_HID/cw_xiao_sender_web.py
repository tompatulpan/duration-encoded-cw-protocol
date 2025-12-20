#!/usr/bin/env python3
"""
CW XIAO Sender with WebSocket Protocol

Reads XIAO SAMD21/RP2040 USB HID device and sends WebSocket JSON messages.
Uses shared xiao_hid_reader module for HID communication.

For internet transmission via Cloudflare Workers / web platform.

Usage:
    python3 cw_xiao_sender_web.py --callsign SM5ABC --mode straight
    python3 cw_xiao_sender_web.py --callsign SM5ABC --mode iambic-b --wpm 25
"""

import sys
import os
import time
import argparse
import json
import asyncio

try:
    import websockets
except ImportError:
    print("Error: websockets library not installed")
    print("Install with: pip3 install websockets")
    sys.exit(1)

# Add test_implementation directory to Python path
sys.path.insert(0, '../test_implementation')

from xiao_hid_reader import XiaoHIDReader
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


async def main():
    parser = argparse.ArgumentParser(
        description="XIAO CW Sender (WebSocket Protocol)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Straight key:
    python3 cw_xiao_sender_web.py --callsign SM5ABC --mode straight
    
  Iambic Mode B paddle:
    python3 cw_xiao_sender_web.py --callsign SM5ABC --mode iambic-b --wpm 25
    
  Custom server:
    python3 cw_xiao_sender_web.py --url wss://cw.example.com --callsign SM5ABC
        """
    )
    
    parser.add_argument('--url', default='ws://localhost:8787',
                       help='WebSocket server URL (default: ws://localhost:8787)')
    parser.add_argument('--callsign', required=True, help='Your amateur radio callsign')
    parser.add_argument('--mode', choices=['straight', 'iambic-a', 'iambic-b'], 
                       default='iambic-b', help='Keying mode (default: iambic-b)')
    parser.add_argument('--wpm', type=int, default=20, help='Keyer speed in WPM (default: 20)')
    parser.add_argument('--device', help='Explicit /dev/hidraw* device path')
    parser.add_argument('--no-audio', action='store_true', help='Disable sidetone')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Validate callsign (basic check)
    if not args.callsign or len(args.callsign) < 3:
        print("Error: Invalid callsign")
        return 1
    
    # Normalize URL - strip any protocol and re-add based on input
    # If user provided http:// use ws://, if https:// use wss://
    # If no protocol, default to ws:// for localhost, wss:// for others
    original_url = args.url
    server_url = args.url.replace('wss://', '').replace('ws://', '').replace('https://', '').replace('http://', '')
    
    # Determine protocol based on original input or hostname
    if original_url.startswith('http://') or original_url.startswith('ws://'):
        ws_url = f"ws://{server_url}"
    elif original_url.startswith('https://') or original_url.startswith('wss://'):
        ws_url = f"wss://{server_url}"
    elif 'localhost' in server_url or '127.0.0.1' in server_url or server_url.startswith('192.168.') or server_url.startswith('10.'):
        ws_url = f"ws://{server_url}"  # Local network - use unencrypted
    else:
        ws_url = f"wss://{server_url}"  # Internet - use encrypted
    
    # Print header
    print("=" * 70)
    print("CW XIAO Sender with WebSocket Protocol")
    print("=" * 70)
    print(f"Callsign: {args.callsign}")
    print(f"Mode: {args.mode.upper()}")
    print(f"Server: {ws_url}")
    print("-" * 70)
    
    # Initialize HID reader
    hid_reader = XiaoHIDReader(device_path=args.device, debug=args.debug)
    if not hid_reader.connect():
        return 1
    
    # Initialize iambic keyer if needed
    keyer = None
    if args.mode in ['iambic-a', 'iambic-b']:
        keyer_mode_letter = 'B' if args.mode == 'iambic-b' else 'A'
        keyer = IambicKeyer(args.wpm, mode=keyer_mode_letter)
        print(f"Keyer: Iambic Mode {keyer_mode_letter}, {args.wpm} WPM")
    
    # Initialize sidetone
    sidetone = None
    if not args.no_audio:
        sidetone = SidetoneGenerator(frequency=600)  # TX frequency
    
    # WebSocket connection variable
    ws = None
    
    # Helper: Send join handshake and wait for confirmation
    async def send_handshake():
        """Send join message and wait for confirmation"""
        nonlocal last_event_time, session_start
        
        join_msg = {
            'type': 'join',
            'roomId': 'main',
            'callsign': args.callsign,
            'muteMyCallsign': True
        }
        
        if args.debug:
            print(f"[WebSocket] Sending join: {join_msg}")
        
        await ws.send(json.dumps(join_msg))
        
        # Wait for confirmation
        timeout = 5.0
        start = time.time()
        while time.time() - start < timeout:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.1)
                data = json.loads(msg)
                
                if data.get('type') in ['joined', 'echo']:
                    if args.debug:
                        print(f"[WebSocket] Handshake confirmed: {data.get('type')}")
                    
                    # Reset timing state after successful handshake (prevents huge gaps)
                    now = time.time()
                    session_start = now
                    last_event_time = now
                    
                    if args.debug:
                        print(f"[WebSocket] Timing state reset")
                    
                    return True
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if args.debug:
                    print(f"[WebSocket] Handshake error: {e}")
                return False
        
        print("[WebSocket] Handshake timeout - no confirmation received")
        return False
    
    # Connect to WebSocket server
    try:
        print(f"Connecting to {ws_url}...")
        # Connect with manual keepalive (Cloudflare Workers requirement)
        ws = await websockets.connect(
            ws_url,
            ping_interval=None,  # Disable automatic pings
            ping_timeout=None    # Use application-level keepalive instead
        )
        
        # Send handshake
        if not await send_handshake():
            raise Exception("Handshake failed - no confirmation from server")
        
        print(f"✓ Connected as {args.callsign} in room 'main'")
        
    except asyncio.TimeoutError:
        print(f"✗ Connection timeout - no response from server")
        hid_reader.close()
        if sidetone:
            sidetone.close()
        return 1
    except Exception as e:
        print(f"Error connecting to WebSocket server: {e}")
        hid_reader.close()
        if sidetone:
            sidetone.close()
        return 1
    
    print("\nReady to transmit (Ctrl+C to exit)")
    if args.debug:
        print("Debug mode: Showing HID data and state changes")
    print("-" * 70)
    
    # State tracking
    key_down = False
    session_start = time.time()
    last_event_time = session_start
    sequence = 0
    loop_count = 0
    
    # Keepalive tracking
    keepalive_task = None
    receive_task = None
    connected = True
    
    # Keepalive loop (prevent idle disconnection)
    async def keepalive_loop():
        """Send keepalive messages every 15 seconds (Cloudflare Workers requirement)"""
        nonlocal connected, ws
        
        while connected and ws:
            try:
                await asyncio.sleep(15)
                if connected and ws:
                    keepalive_msg = {'type': 'keepalive'}
                    await ws.send(json.dumps(keepalive_msg))
                    if args.debug:
                        print("[DEBUG] Keepalive sent")
            except Exception as e:
                if args.debug:
                    print(f"[DEBUG] Keepalive failed: {e}")
                break
    
    # Receive loop (handle keepalive_ack and maintain connection)
    async def receive_loop():
        """Receive events from server (keepalive acks and room events)"""
        nonlocal connected, ws
        
        while connected and ws:
            try:
                message = await ws.recv()
                data = json.loads(message)
                
                msg_type = data.get('type')
                
                if msg_type == 'keepalive_ack':
                    if args.debug:
                        print("[DEBUG] Keepalive acknowledged")
                
                elif msg_type in ['peer_joined', 'peer_left']:
                    if args.debug:
                        print(f"[DEBUG] Room event: {msg_type}")
                
            except websockets.exceptions.ConnectionClosed:
                print("\n✗ Connection closed by server")
                connected = False
                break
            except Exception as e:
                if args.debug:
                    print(f"[DEBUG] Receive error: {e}")
                break
    
    # WebSocket reconnection helper
    async def ws_send_with_reconnect(ws_ref, message_dict):
        """Send WebSocket message with automatic reconnection on failure"""
        nonlocal ws, connected, keepalive_task, receive_task
        
        max_reconnect_attempts = 5
        reconnect_delay = 2.0
        
        # Validate duration before sending (prevent protocol overflow)
        duration_ms = message_dict.get('duration_ms', 0)
        if duration_ms > 65535:
            if args.debug:
                print(f"[WebSocket] ⚠ Duration {duration_ms}ms exceeds max (65535ms), clamping")
            message_dict['duration_ms'] = 65535
        
        # First, try to send
        try:
            await ws.send(json.dumps(message_dict))
            return True
        except (websockets.exceptions.ConnectionClosed, 
                websockets.exceptions.WebSocketException,
                Exception) as e:
            print(f"\n[WebSocket] Connection lost: {e}")
            print(f"[WebSocket] Attempting to reconnect...")
            
            # Try to reconnect with multiple attempts
            for attempt in range(max_reconnect_attempts):
                try:
                    await asyncio.sleep(reconnect_delay)
                    
                    # Reconnect
                    ws = await websockets.connect(ws_url, ping_interval=None, ping_timeout=None)
                    print(f"[WebSocket] ✓ Reconnected to {ws_url}")
                    
                    # Re-send handshake (CRITICAL FIX)
                    if not await send_handshake():
                        raise Exception("Handshake failed after reconnection")
                    
                    print(f"[WebSocket] ✓ Handshake complete")
                    
                    # Restart keepalive and receive tasks
                    connected = True
                    if keepalive_task:
                        keepalive_task.cancel()
                    if receive_task:
                        receive_task.cancel()
                    keepalive_task = asyncio.create_task(keepalive_loop())
                    receive_task = asyncio.create_task(receive_loop())
                    
                    # Try to send the original message
                    try:
                        await ws.send(json.dumps(message_dict))
                        return True
                    except Exception as send_err:
                        print(f"[WebSocket] Send after reconnection failed: {send_err}")
                        continue
                        
                except Exception as reconnect_err:
                    if attempt < max_reconnect_attempts - 1:
                        print(f"[WebSocket] Reconnection attempt {attempt + 1}/{max_reconnect_attempts} failed, retrying...")
                    else:
                        print(f"[WebSocket] ✗ Could not reconnect after {max_reconnect_attempts} attempts")
                        print(f"[WebSocket] Continuing without connection (packets will be dropped)")
                        return False
            
            return False
    
    # Helper function to read current paddle states (used by iambic keyer)
    def read_paddle_states():
        """Read current paddle states - called by keyer during elements"""
        return hid_reader.read_paddles()
    
    # Pending events queue (keyer is sync, we send async later)
    pending_events = []
    
    # Helper function for keyer to send events (synchronous wrapper)
    def send_element(key_down_state, duration_ms):
        """Send a CW element (used by iambic keyer)
        
        Args:
            key_down_state: True for DOWN, False for UP
            duration_ms: Element duration (dit/dah length or spacing)
        """
        nonlocal last_event_time, sequence
        
        now = time.time()
        
        # Control sidetone immediately (local audio feedback)
        if sidetone:
            sidetone.set_key(key_down_state)
        
        # Calculate duration of PREVIOUS state (protocol semantics)
        previous_duration_ms = int((now - last_event_time) * 1000)
        previous_duration_ms = min(previous_duration_ms, 65535)
        
        # Calculate timestamp (ms since session start)
        timestamp_ms = int((now - session_start) * 1000)
        
        # Create WebSocket JSON message
        message = {
            'type': 'cw_event',
            'callsign': args.callsign,
            'key_down': key_down_state,
            'duration_ms': previous_duration_ms,
            'timestamp_ms': timestamp_ms,
            'sequence': sequence
        }
        
        # Queue for async sending
        pending_events.append(message)
        sequence = (sequence + 1) % 256
        
        # Debug output - show what we SENT in packet (previous state duration)
        state_str = "DOWN" if key_down_state else "UP"
        if args.debug:
            print(f"[SEND] {state_str} {previous_duration_ms:5d}ms (ts={timestamp_ms}ms, seq={sequence-1})")
        else:
            print(f"[KEY] {state_str:4s} {previous_duration_ms:5d}ms")
        
        last_event_time = now
    
    # Start background tasks
    keepalive_task = asyncio.create_task(keepalive_loop())
    receive_task = asyncio.create_task(receive_loop())
    
    try:
        while True:
            loop_count += 1
            
            # Show heartbeat every 5000 loops when in debug mode
            if args.debug and loop_count % 5000 == 0:
                print(f"[LOOP] Iteration {loop_count}, reads: {hid_reader.read_count}")
            
            # Iambic mode - use keyer logic
            if keyer:
                # Keyer is synchronous, queues events
                keyer.update(read_paddle_states, send_element)
                
                # Send any queued events
                while pending_events:
                    message = pending_events.pop(0)
                    await ws_send_with_reconnect(ws, message)
                
                await asyncio.sleep(0.001)  # 1ms polling
            
            # Straight key mode
            else:
                dit, dah = hid_reader.read_paddles()
                new_key_down = dit or dah
                
                # Detect state change
                if new_key_down != key_down:
                    now = time.time()
                    
                    # Control sidetone immediately (local audio feedback)
                    if sidetone:
                        sidetone.set_key(new_key_down)
                    
                    # Calculate duration of previous state
                    duration_ms = int((now - last_event_time) * 1000)
                    duration_ms = min(duration_ms, 65535)
                    
                    # Calculate timestamp (ms since session start)
                    timestamp_ms = int((now - session_start) * 1000)
                    
                    # Create WebSocket JSON message
                    message = {
                        'type': 'cw_event',
                        'callsign': args.callsign,
                        'key_down': new_key_down,
                        'duration_ms': duration_ms,
                        'timestamp_ms': timestamp_ms,
                        'sequence': sequence
                    }
                    
                    # Send message
                    if not await ws_send_with_reconnect(ws, message):
                        print("\n[ERROR] Connection lost and could not reconnect.")
                        # Continue with local sidetone even without connection
                    sequence = (sequence + 1) % 256
                    
                    # Update state
                    key_down = new_key_down
                    last_event_time = now
                    
                    # Debug output
                    state_str = "DOWN" if key_down else "UP"
                    if args.debug:
                        print(f"[SEND] {state_str} {duration_ms:5d}ms (ts={timestamp_ms}ms, seq={sequence-1})")
                    else:
                        print(f"[KEY] {state_str:4s} {duration_ms:5d}ms")
                
                await asyncio.sleep(0.001)  # 1ms polling
    
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    
    finally:
        # Stop background tasks
        connected = False
        if keepalive_task:
            keepalive_task.cancel()
        if receive_task:
            receive_task.cancel()
        
        # Wait briefly for task cleanup
        try:
            await asyncio.sleep(0.1)
        except:
            pass
        
        # Send final UP event if key was down
        if key_down and last_event_time:
            # Stop sidetone
            if sidetone:
                sidetone.set_key(False)
            
            duration_ms = int((time.time() - last_event_time) * 1000)
            duration_ms = min(duration_ms, 65535)
            timestamp_ms = int((time.time() - session_start) * 1000)
            
            message = {
                'type': 'cw_event',
                'callsign': args.callsign,
                'key_down': False,
                'duration_ms': duration_ms,
                'timestamp_ms': timestamp_ms,
                'sequence': sequence
            }
            await ws_send_with_reconnect(ws, message)
        
        # Send EOT
        if connected:
            eot_msg = {
                'type': 'cw_eot',
                'callsign': args.callsign
            }
            try:
                await ws.send(json.dumps(eot_msg))
                await asyncio.sleep(0.1)
            except:
                pass
        
        # Cleanup
        if sidetone:
            sidetone.close()
        hid_reader.close()
        await ws.close()
        
        print("Disconnected")
    
    return 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n\nShutdown requested (Ctrl+C)")
        sys.exit(0)
