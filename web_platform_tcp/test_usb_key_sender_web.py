#!/usr/bin/env python3
"""
Test USB Key Sender Web - Simulate keyboard input for testing
Tests the WebSocket connection without requiring actual USB hardware
"""

import asyncio
import websockets
import json
import time
import argparse


class SimulatedKeySender:
    """Simulate CW key events for testing"""
    
    def __init__(self, server_url, callsign, room_id="main", debug=False):
        self.server_url = server_url
        self.callsign = callsign
        self.room_id = room_id
        self.debug = debug
        
        self.ws = None
        self.connected = False
        self.transmission_start = None
        self.sequence_number = 0
        self.events_sent = 0
        self.events_received = 0
    
    async def connect(self):
        """Connect to WebSocket server"""
        try:
            print(f"Connecting to {self.server_url}...")
            
            self.ws = await websockets.connect(
                self.server_url,
                ping_interval=None,
                ping_timeout=None
            )
            
            # Send join message
            join_msg = {
                'type': 'join',
                'roomId': self.room_id,
                'callsign': self.callsign
            }
            await self.ws.send(json.dumps(join_msg))
            
            # Wait for response
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)
            
            if data.get('type') in ['joined', 'echo']:
                print(f"✓ Connected as {self.callsign}")
                self.connected = True
                self.transmission_start = time.time()
                return True
                
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    async def send_event(self, key_down, duration_ms):
        """Send CW event"""
        if not self.transmission_start:
            self.transmission_start = time.time()
            timestamp_ms = 0
        else:
            timestamp_ms = int((time.time() - self.transmission_start) * 1000)
        
        event = {
            'type': 'cw_event',
            'callsign': self.callsign,
            'key_down': key_down,
            'duration_ms': int(duration_ms),
            'timestamp_ms': timestamp_ms,
            'sequence': self.sequence_number
        }
        
        self.sequence_number = (self.sequence_number + 1) % 256
        
        await self.ws.send(json.dumps(event))
        self.events_sent += 1
        
        if self.debug:
            print(f"[SEND] {key_down} dur={duration_ms}ms ts={timestamp_ms}ms seq={event['sequence']}")
        else:
            print("▄" if key_down else "▀", end='', flush=True)
    
    async def receive_loop(self):
        """Receive events (echo mode)"""
        while self.connected:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                if data.get('type') == 'cw_event':
                    self.events_received += 1
                    
                    if self.debug:
                        sent_ts = data.get('timestamp_ms', 0)
                        now_ts = int((time.time() - self.transmission_start) * 1000)
                        latency = now_ts - sent_ts
                        print(f"\n[ECHO] Received: {data['key_down']} dur={data['duration_ms']}ms latency={latency}ms")
                        
            except websockets.exceptions.ConnectionClosed:
                print("\n✗ Connection closed")
                self.connected = False
                break
            except Exception as e:
                if self.debug:
                    print(f"\n[DEBUG] Receive error: {e}")
                break
    
    async def send_test_pattern(self, wpm=25):
        """Send test CW pattern - 'PARIS PARIS' to test word spaces
        
        CORRECTED PROTOCOL:
        - key_down=true: Transition TO DOWN, duration = PREVIOUS UP time (spacing)
        - key_down=false: Transition TO UP, duration = PREVIOUS DOWN time (element)
        """
        dit_duration = 1200 / wpm
        dah_duration = dit_duration * 3
        element_space = dit_duration
        letter_space = dit_duration * 3
        word_space = dit_duration * 7
        
        # PARIS in Morse code
        paris = [
            ('P', ['.', '-', '-', '.']),  # .--. 
            ('A', ['.', '-']),             # .-
            ('R', ['.', '-', '.']),        # .-.
            ('I', ['.', '.']),             # ..
            ('S', ['.', '.', '.'])         # ...
        ]
        
        print(f"\n✓ Sending test pattern 'PARIS PARIS PARIS' at {wpm} WPM")
        print(f"  Dit: {dit_duration:.0f}ms, Dah: {dah_duration:.0f}ms")
        print(f"  Word space: {word_space:.0f}ms (should appear between words)")
        print(f"  (Ctrl+C to stop)\n")
        
        try:
            previous_spacing = 0  # Track spacing before each element
            
            for word_idx in range(3):  # Send PARIS 3 times
                for char_idx, (char, pattern) in enumerate(paris):
                    is_last_char = (char_idx == len(paris) - 1)
                    
                    print(char, end='', flush=True)
                    
                    # Send each element in the character
                    for elem_idx, element in enumerate(pattern):
                        is_last_element = (elem_idx == len(pattern) - 1)
                        
                        # Element duration
                        element_dur = dah_duration if element == '-' else dit_duration
                        
                        # Transition TO DOWN: was UP for previous_spacing
                        await self.send_event(True, previous_spacing)
                        await asyncio.sleep(element_dur / 1000.0)  # Key is DOWN
                        
                        # Transition TO UP: was DOWN for element_dur
                        await self.send_event(False, element_dur)
                        
                        # Calculate spacing AFTER this element (for next DOWN transition)
                        if not is_last_element:
                            # Between elements within character
                            previous_spacing = element_space
                            await asyncio.sleep(element_space / 1000.0)
                        elif is_last_char:
                            # Last element of last char in word: word space
                            previous_spacing = word_space
                            await asyncio.sleep(word_space / 1000.0)
                            if self.debug:
                                print(f"\n[DEBUG] Word space: {word_space:.0f}ms")
                        else:
                            # Last element in character: letter space
                            previous_spacing = letter_space
                            await asyncio.sleep(letter_space / 1000.0)
                            if self.debug:
                                print(f"\n[DEBUG] Letter space: {letter_space:.0f}ms")
                
                # Print space indicator after words
                if word_idx < 2:
                    print(' ', end='', flush=True)
            
            print(f"\n\n✓ Test pattern complete")
            print(f"  Events sent: {self.events_sent}")
            print(f"  Events received: {self.events_received}")
            
            if self.events_sent > 0 and self.events_received > 0:
                echo_rate = 100 * self.events_received / self.events_sent
                print(f"  Echo rate: {echo_rate:.1f}%")
                
                if self.events_received == self.events_sent:
                    print("  ✓ All events echoed back successfully!")
                else:
                    print(f"  ⚠ Missing {self.events_sent - self.events_received} events")
            
        except KeyboardInterrupt:
            print("\n\n✓ Stopped by user")
    
    async def run(self):
        """Main run loop"""
        if not await self.connect():
            return
        
        try:
            # Start receive loop and send test pattern
            receive_task = asyncio.create_task(self.receive_loop())
            send_task = asyncio.create_task(self.send_test_pattern())
            
            await send_task
            
            # Wait a bit for final echoes
            await asyncio.sleep(1.0)
            
            # Cancel receive task
            receive_task.cancel()
            
        finally:
            if self.ws:
                await self.ws.close()


def main():
    parser = argparse.ArgumentParser(
        description='Test USB Key Sender Web (simulated keyboard input)'
    )
    
    parser.add_argument('--server', required=True,
                        help='WebSocket server URL')
    parser.add_argument('--callsign', default='TEST',
                        help='Callsign (default: TEST)')
    parser.add_argument('--room', default='main',
                        help='Room ID (default: main)')
    parser.add_argument('--wpm', type=int, default=25,
                        help='Test pattern speed in WPM (default: 25)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    
    args = parser.parse_args()
    
    sender = SimulatedKeySender(
        server_url=args.server,
        callsign=args.callsign,
        room_id=args.room,
        debug=args.debug
    )
    
    asyncio.run(sender.run())


if __name__ == '__main__':
    main()
