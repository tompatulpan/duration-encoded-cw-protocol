#!/usr/bin/env python3
"""
CW Studio Client - Send CW events directly to CW Studio server
No audio routing needed - server generates sidetone for listeners
"""
import sys
import os
import json
import asyncio
import websockets

# Import from parent directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cw_usb_key_sender_with_decoder import IambicKeyer
import serial
import time


class CWStudioClient:
    def __init__(self, server_url, room_id, callsign, serial_port, mode='iambic', wpm=20, keyer_mode='B'):
        self.server_url = server_url
        self.room_id = room_id
        self.callsign = callsign
        self.serial_port = serial_port
        self.mode = mode
        self.wpm = wpm
        self.keyer_mode = keyer_mode
        self.ws = None
        self.peer_id = f"{callsign}_{int(time.time())}"
        
        # Setup keyer
        if mode == 'iambic':
            self.keyer = IambicKeyer(wpm=wpm, mode=keyer_mode)
        else:
            self.keyer = None
        
        # Setup serial port
        try:
            self.ser = serial.Serial(
                port=serial_port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.001
            )
            print(f"✓ Serial port {serial_port} opened")
        except Exception as e:
            print(f"✗ Failed to open serial port: {e}")
            sys.exit(1)
    
    async def connect(self):
        """Connect to CW Studio WebSocket server"""
        print(f"Connecting to {self.server_url}...")
        try:
            self.ws = await websockets.connect(self.server_url)
            
            # Send join message
            join_msg = {
                'type': 'join',
                'roomId': self.room_id,
                'peerId': self.peer_id,
                'callsign': self.callsign,
                'isSender': True  # Mark as CW sender (no WebRTC)
            }
            await self.ws.send(json.dumps(join_msg))
            print(f"✓ Sent join request for room '{self.room_id}'")
            
            # Wait for confirmation
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)
            
            if data['type'] == 'joined':
                print(f"✓ Connected as {self.callsign} (peer: {self.peer_id})")
                return True
            else:
                print(f"✗ Unexpected response: {data}")
                return False
                
        except asyncio.TimeoutError:
            print("✗ Connection timeout")
            return False
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    async def send_cw_event(self, event_type, duration_ms=0):
        """Send CW event to server
        
        Args:
            event_type: 'tone_start' or 'tone_end'
            duration_ms: tone duration in milliseconds (for tone_end)
        """
        if self.ws:
            try:
                msg = {
                    'type': 'cw_event',
                    'roomId': self.room_id,
                    'peerId': self.peer_id,
                    'callsign': self.callsign,
                    'event': event_type,
                    'duration': duration_ms,
                    'timestamp': int(time.time() * 1000)
                }
                print(f"→ Sending: {event_type} ({duration_ms}ms)", end=' ', flush=True)
                await self.ws.send(json.dumps(msg))
            except Exception as e:
                print(f"\n✗ Failed to send event: {e}")
    
    async def poll_iambic(self):
        """Poll iambic paddles and send events"""
        print("✓ Iambic keyer ready")
        
        # Create a callback to send events
        def send_element(key_down, duration_ms):
            """Callback for keyer to send events (runs synchronously during keyer update)"""
            # Store events to send asynchronously later
            # tone_start has no duration, tone_end has the duration
            event_type = 'tone_start' if key_down else 'tone_end'
            dur = 0 if key_down else int(duration_ms)
            self.pending_events.append((event_type, dur))
        
        self.pending_events = []
        
        while True:
            try:
                # Read paddle states (CTS=dit, DSR=dah)
                dit_pressed = self.ser.cts
                dah_pressed = self.ser.dsr
                
                # Update keyer (this will call send_element callback)
                self.keyer.update(dit_pressed, dah_pressed, send_element)
                
                # Send any pending events
                while self.pending_events:
                    event_type, duration = self.pending_events.pop(0)
                    await self.send_cw_event(event_type, duration)
                    if event_type == 'tone_start':
                        print("▄", end='', flush=True)
                    else:
                        print("▀", end='', flush=True)
                
                # Small sleep to prevent busy loop
                await asyncio.sleep(0.001)
                    
            except Exception as e:
                print(f"\n✗ Polling error: {e}")
                import traceback
                traceback.print_exc()
                break
    
    async def poll_straight(self):
        """Poll straight key and send events"""
        key_down = False
        key_down_time = 0
        
        print("✓ Straight key ready")
        
        while True:
            try:
                # Read key state (CTS pin)
                current_state = self.ser.cts
                
                if current_state and not key_down:
                    # Key pressed
                    key_down = True
                    key_down_time = time.time()
                    await self.send_cw_event('tone_start')
                    print("▄", end='', flush=True)
                
                elif not current_state and key_down:
                    # Key released
                    duration = int((time.time() - key_down_time) * 1000)
                    await self.send_cw_event('tone_end', duration)
                    key_down = False
                    print("▀", end='', flush=True)
                
                await asyncio.sleep(0.001)
                
            except Exception as e:
                print(f"\n✗ Polling error: {e}")
                break
    
    async def heartbeat(self):
        """Send periodic heartbeat to keep connection alive"""
        while True:
            try:
                await asyncio.sleep(30)
                if self.ws:
                    await self.ws.send(json.dumps({
                        'type': 'ping',
                        'peerId': self.peer_id
                    }))
            except Exception:
                break
    
    async def receive_messages(self):
        """Receive messages from server (for debugging)"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg_type = data.get('type', 'unknown')
                
                if msg_type == 'peer-joined':
                    print(f"\n✓ Listener joined: {data.get('callsign', 'unknown')}")
                elif msg_type == 'peer-left':
                    print(f"\n✓ Listener left: {data.get('callsign', 'unknown')}")
                elif msg_type == 'cw_event_ack':
                    print("✓", end='', flush=True)
                elif msg_type == 'error':
                    print(f"\n✗ Server error: {data.get('message', 'unknown')}")
                else:
                    print(f"\n← Received: {msg_type}")
        except Exception as e:
            print(f"\n✗ Connection closed: {e}")
    
    async def run(self):
        """Main loop"""
        if await self.connect():
            try:
                # Run polling and message receiving concurrently
                if self.mode == 'iambic':
                    poll_task = asyncio.create_task(self.poll_iambic())
                else:
                    poll_task = asyncio.create_task(self.poll_straight())
                
                recv_task = asyncio.create_task(self.receive_messages())
                heartbeat_task = asyncio.create_task(self.heartbeat())
                
                # Wait for any task to complete (or Ctrl+C)
                await asyncio.gather(poll_task, recv_task, heartbeat_task)
                
            except KeyboardInterrupt:
                print("\n\n73! Disconnecting...")
            finally:
                if self.ws:
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                if self.ser:
                    self.ser.close()


async def main():
    if len(sys.argv) < 4:
        print("\n" + "=" * 70)
        print("CW Studio Client - Direct Protocol Connection")
        print("=" * 70)
        print("\nNo audio routing needed! Server generates sidetone for listeners.")
        print("\nUsage:")
        print("  python3 cw_studio_client.py <server_url> <room_id> <callsign> <mode> [wpm] [port]")
        print("\nExamples:")
        print("  # Production server:")
        print("  python3 cw_studio_client.py wss://cw-studio-signaling.data4-9de.workers.dev/ws \\")
        print("    practice-room SM0ONR iambic-b 25 /dev/ttyUSB0")
        print()
        print("  # Local development:")
        print("  python3 cw_studio_client.py ws://localhost:8787/ws \\")
        print("    test-room W1ABC straight 20 /dev/ttyUSB0")
        print("\nModes: straight, iambic-a, iambic-b")
        print("Default: 25 WPM, /dev/ttyUSB0")
        print("=" * 70)
        print()
        return
    
    server_url = sys.argv[1]
    room_id = sys.argv[2]
    callsign = sys.argv[3].upper()
    mode_arg = sys.argv[4] if len(sys.argv) > 4 else 'iambic-b'
    wpm = int(sys.argv[5]) if len(sys.argv) > 5 else 25
    serial_port = sys.argv[6] if len(sys.argv) > 6 else '/dev/ttyUSB0'
    
    # Parse mode
    if mode_arg.startswith('iambic'):
        mode = 'iambic'
        keyer_mode = 'B' if mode_arg == 'iambic-b' else 'A'
    else:
        mode = 'straight'
        keyer_mode = 'B'
    
    print("\n" + "=" * 70)
    print(f"CW Studio Client - {callsign}")
    print("=" * 70)
    print(f"Room:   {room_id}")
    print(f"Mode:   {mode_arg} @ {wpm} WPM")
    print(f"Serial: {serial_port}")
    print(f"Server: {server_url}")
    print("=" * 70)
    print("\nListeners in the room will hear your CW through the web interface!")
    print("Press Ctrl+C to quit\n")
    
    client = CWStudioClient(server_url, room_id, callsign, serial_port, mode, wpm, keyer_mode)
    await client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n73!")
