#!/usr/bin/env python3
"""
USB Key Sender - Web Platform (TCP Timestamp Protocol via WebSocket)
Read physical CW key via USB serial adapter and transmit to web platform
Supports: Straight key, Iambic Mode A, Iambic Mode B

Usage:
    python3 cw_usb_key_sender_web.py --server wss://your-server.workers.dev [options]

Examples:
    # Straight key (default)
    python3 cw_usb_key_sender_web.py --server wss://cw-relay.workers.dev --callsign SM5ABC
    
    # Iambic paddles (Mode B)
    python3 cw_usb_key_sender_web.py --server wss://cw-relay.workers.dev --callsign SM5ABC --mode iambic-b --wpm 25
    
    # Connect to room
    python3 cw_usb_key_sender_web.py --server wss://cw-relay.workers.dev --callsign SM5ABC --room practice
    
    # Test with echo mode (receive back your own events)
    python3 cw_usb_key_sender_web.py --server wss://cw-relay.workers.dev --callsign TEST --echo
"""

import sys
import os
import json
import asyncio
import websockets
import time
import serial
import serial.tools.list_ports
import argparse
import threading

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'test_implementation'))

# Try to import audio library
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


class SidetoneGenerator:
    """Generate sidetone audio using PyAudio"""
    def __init__(self, frequency=600, sample_rate=48000, volume=0.3):
        if not AUDIO_AVAILABLE:
            self.enabled = False
            return
            
        self.enabled = True
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.volume = volume
        
        # Audio state
        self.key_down = False
        self.phase = 0.0
        
        # Initialize PyAudio
        try:
            self.p = pyaudio.PyAudio()
            self.stream = self.p.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=128,  # Low latency
                stream_callback=self._audio_callback
            )
            self.stream.start_stream()
            print(f"✓ TX Sidetone initialized ({frequency}Hz)")
        except Exception as e:
            print(f"✗ Sidetone failed: {e}")
            self.enabled = False
            if hasattr(self, 'p'):
                self.p.terminate()
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Generate audio samples"""
        if self.key_down:
            # Generate sine wave with smooth envelope
            samples = np.arange(frame_count)
            omega = 2.0 * np.pi * self.frequency / self.sample_rate
            audio = self.volume * np.sin(omega * samples + self.phase).astype(np.float32)
            self.phase = (self.phase + omega * frame_count) % (2.0 * np.pi)
        else:
            # Silence
            audio = np.zeros(frame_count, dtype=np.float32)
        
        return (audio.tobytes(), pyaudio.paContinue)
    
    def set_key(self, key_down):
        """Set key state (thread-safe)"""
        self.key_down = key_down
    
    def close(self):
        """Cleanup audio resources"""
        if self.enabled:
            self.stream.stop_stream()
            self.stream.close()
            self.p.terminate()


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
        self.last_element_time = None  # Track idle time for letter/word spaces
        
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
                
                # Send dit (DOWN with dit duration, UP with element_space)
                # Timestamp protocol handles absolute timing automatically
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                self.last_element_time = time.time()
                
                # Check if dah was pressed during dit (Mode B memory)
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
                    
            elif dah_paddle:
                self.dit_memory = False
                self.dah_memory = False
                self.state = self.DAH
                
                # Send dah (DOWN with dah duration, UP with element_space)
                # Timestamp protocol handles absolute timing automatically
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                self.last_element_time = time.time()
                
                # Check if dit was pressed during dah (Mode B memory)
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            
            return self.state != self.IDLE
        
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
                self.last_element_time = time.time()
                
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
                self.last_element_time = time.time()
                
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
                self.last_element_time = time.time()
                
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
                self.last_element_time = time.time()
                
                # Mode B: Check for dit during dah
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                # No memory, return to idle
                self.state = self.IDLE
                return False
                
        return True  # Still active


class USBKeyWebSender:
    """Send CW events from USB key to web platform via WebSocket"""
    
    def __init__(self, server_url, callsign, room_id="main", serial_port=None, 
                 mode='straight', wpm=20, keyer_mode='B', sidetone=True, 
                 echo_mode=False, debug=False):
        self.server_url = server_url
        self.callsign = callsign
        self.room_id = room_id
        self.serial_port = serial_port
        self.mode = mode
        self.wpm = wpm
        self.keyer_mode = keyer_mode
        self.echo_mode = echo_mode
        self.debug = debug
        
        # WebSocket connection
        self.ws = None
        self.connected = False
        self.running = False
        
        # Timing for TCP-TS protocol
        self.transmission_start = None
        self.sequence_number = 0
        
        # Setup sidetone
        self.sidetone = None
        if sidetone and AUDIO_AVAILABLE:
            self.sidetone = SidetoneGenerator(frequency=600)  # TX frequency
        elif sidetone:
            print("⚠ pyaudio not available - install with: pip3 install pyaudio")
        
        # Setup keyer
        if mode in ['iambic-a', 'iambic-b']:
            keyer_mode = 'A' if mode == 'iambic-a' else 'B'
            self.keyer = IambicKeyer(wpm=wpm, mode=keyer_mode)
            print(f"✓ Iambic keyer Mode {keyer_mode} initialized ({wpm} WPM)")
        else:
            self.keyer = None
            print(f"✓ Straight key mode")
        
        # Setup serial port
        if not serial_port:
            serial_port = self._auto_detect_port()
        
        try:
            self.ser = serial.Serial(
                port=serial_port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.001  # Non-blocking
            )
            print(f"✓ Serial port {serial_port} opened")
        except Exception as e:
            print(f"✗ Failed to open serial port: {e}")
            sys.exit(1)
        
        # Event queue for async sending
        self.pending_events = []
        
        # Statistics
        self.events_sent = 0
        self.events_received = 0
        self.start_time = None
    
    def _auto_detect_port(self):
        """Auto-detect USB serial port"""
        ports = list(serial.tools.list_ports.comports())
        
        if len(ports) == 0:
            print("✗ No serial ports found")
            sys.exit(1)
        elif len(ports) == 1:
            print(f"✓ Auto-detected serial port: {ports[0].device}")
            return ports[0].device
        else:
            print("\nAvailable serial ports:")
            for i, port in enumerate(ports):
                print(f"  {i+1}. {port.device} - {port.description}")
            
            while True:
                try:
                    choice = input("\nSelect port (1-{}): ".format(len(ports)))
                    idx = int(choice) - 1
                    if 0 <= idx < len(ports):
                        return ports[idx].device
                except (ValueError, KeyboardInterrupt):
                    print("\n✗ Cancelled")
                    sys.exit(1)
    
    async def connect(self, max_retries=5):
        """Connect to WebSocket server with retry logic"""
        for attempt in range(max_retries):
            try:
                print(f"Connecting to {self.server_url}... (attempt {attempt + 1}/{max_retries})")
                
                # Connect with manual keepalive (Cloudflare Workers requirement)
                self.ws = await websockets.connect(
                    self.server_url,
                    ping_interval=None,  # Disable automatic pings
                    ping_timeout=None    # Disable ping timeout
                )
                
                # Send join message
                join_msg = {
                    'type': 'join',
                    'roomId': self.room_id,
                    'callsign': self.callsign
                }
                await self.ws.send(json.dumps(join_msg))
                
                # Wait for join confirmation
                response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                data = json.loads(response)
                
                if data.get('type') == 'joined':
                    print(f"✓ Connected as {self.callsign} in room '{self.room_id}'")
                    self.connected = True
                    self.start_time = time.time()
                    return True
                elif data.get('type') == 'echo':
                    # Echo mode - no room support
                    print(f"✓ Connected in echo mode (single-user testing)")
                    self.connected = True
                    self.echo_mode = True
                    self.start_time = time.time()
                    return True
                    
            except asyncio.TimeoutError:
                print(f"✗ Connection timeout")
            except Exception as e:
                print(f"✗ Connection failed: {e}")
            
            if attempt < max_retries - 1:
                delay = 2 ** attempt  # Exponential backoff
                print(f"  Retrying in {delay}s...")
                await asyncio.sleep(delay)
        
        print("✗ Failed to connect after {} attempts".format(max_retries))
        return False
    
    async def keepalive_loop(self):
        """Send keepalive messages every 15 seconds (Cloudflare Workers requirement)"""
        while self.connected and self.ws:
            try:
                await asyncio.sleep(15)
                if self.connected and self.ws:
                    keepalive_msg = {'type': 'keepalive'}
                    await self.ws.send(json.dumps(keepalive_msg))
                    if self.debug:
                        print("[DEBUG] Keepalive sent")
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG] Keepalive failed: {e}")
                break
    
    async def receive_loop(self):
        """Receive events from server (for echo mode testing)"""
        if not self.echo_mode:
            return  # Only run in echo mode
        
        print("✓ Echo mode: will receive back your own events")
        
        while self.connected and self.ws:
            try:
                message = await self.ws.recv()
                data = json.dumps(message)
                
                if data.get('type') == 'cw_event':
                    self.events_received += 1
                    
                    # Calculate round-trip latency
                    if 'timestamp_ms' in data:
                        sent_ts = data['timestamp_ms']
                        now_ts = int((time.time() - self.transmission_start) * 1000) if self.transmission_start else 0
                        latency = now_ts - sent_ts
                        
                        if self.debug:
                            print(f"\n[ECHO] Received: {data['key_down']} duration={data['duration_ms']}ms latency={latency}ms")
                    
            except websockets.exceptions.ConnectionClosed:
                print("\n✗ Connection closed")
                self.connected = False
                break
            except Exception as e:
                if self.debug:
                    print(f"\n[DEBUG] Receive error: {e}")
                break
    
    def _send_event(self, key_down, duration_ms):
        """
        Create event with TCP-TS timing (synchronous, called from keyer)
        Event is queued for async sending
        """
        # Initialize transmission start on first event
        if self.transmission_start is None:
            self.transmission_start = time.time()
            timestamp_ms = 0
        else:
            # Calculate timestamp relative to transmission start (TCP-TS protocol)
            timestamp_ms = int((time.time() - self.transmission_start) * 1000)
        
        # Control sidetone immediately (synchronous timing)
        if self.sidetone:
            self.sidetone.set_key(key_down)
        
        # Create event (matching web platform format)
        event = {
            'type': 'cw_event',
            'callsign': self.callsign,
            'key_down': key_down,
            'duration_ms': int(duration_ms),
            'timestamp_ms': timestamp_ms,
            'sequence': self.sequence_number
        }
        
        self.sequence_number = (self.sequence_number + 1) % 256
        
        # Queue for async sending
        self.pending_events.append(event)
        
        # Visual feedback
        if key_down:
            print("▄", end='', flush=True)
        else:
            print("▀", end='', flush=True)
    
    async def send_queued_events(self):
        """Send queued events asynchronously"""
        while self.pending_events:
            event = self.pending_events.pop(0)
            try:
                await self.ws.send(json.dumps(event))
                self.events_sent += 1
                
                if self.debug:
                    print(f"\n[SEND] {event['key_down']} dur={event['duration_ms']}ms ts={event['timestamp_ms']}ms")
                    
            except Exception as e:
                print(f"\n✗ Send failed: {e}")
                self.connected = False
                break
    
    async def poll_straight_key(self):
        """Poll straight key and send events"""
        last_key_state = False
        last_change_time = time.time()
        
        print("✓ Ready - press key to send CW")
        print("  (Ctrl+C to quit)")
        
        while self.running and self.connected:
            try:
                # Read key state (CTS = key down)
                current_key_state = self.ser.cts
                
                # Detect state change
                if current_key_state != last_key_state:
                    current_time = time.time()
                    duration_ms = (current_time - last_change_time) * 1000.0
                    
                    # Send previous state with its measured duration
                    # When key releases: sends DOWN(element_duration)
                    # When key presses: sends UP(spacing_duration)
                    self._send_event(last_key_state, duration_ms)
                    
                    last_key_state = current_key_state
                    last_change_time = current_time
                
                # Send any queued events
                await self.send_queued_events()
                
                # Small sleep to prevent busy loop
                await asyncio.sleep(0.001)
                
            except Exception as e:
                print(f"\n✗ Polling error: {e}")
                break
    
    def _keyer_thread(self):
        """Keyer thread - runs blocking keyer logic"""
        while self.running and self.connected:
            try:
                # Read paddle states (CTS=dit, DSR=dah)
                dit_pressed = self.ser.cts
                dah_pressed = self.ser.dsr
                
                # Update keyer (this will call _send_event callback synchronously)
                # The keyer does blocking time.sleep() calls internally
                active = self.keyer.update(dit_pressed, dah_pressed, self._send_event)
                
                # Small sleep when idle to prevent busy loop
                if not active:
                    time.sleep(0.01)
                
            except Exception as e:
                print(f"\n✗ Keyer thread error: {e}")
                break
    
    async def poll_iambic_key(self):
        """Poll iambic paddles and send events (async wrapper)"""
        print("✓ Ready - use paddles to send CW")
        print("  (Ctrl+C to quit)")
        
        # Start keyer in separate thread (keyer needs blocking sleep)
        keyer_thread = threading.Thread(target=self._keyer_thread, daemon=True)
        keyer_thread.start()
        
        # Main async loop sends queued events
        while self.running and self.connected:
            try:
                # Send any queued events
                await self.send_queued_events()
                
                # Small sleep
                await asyncio.sleep(0.01)
                
            except Exception as e:
                print(f"\n✗ Polling error: {e}")
                break
        
        # Wait for keyer thread to finish
        keyer_thread.join(timeout=1.0)
    
    async def run(self):
        """Main run loop"""
        self.running = True
        
        # Connect to server
        if not await self.connect():
            return
        
        try:
            # Start tasks
            tasks = []
            
            # Keepalive task
            tasks.append(asyncio.create_task(self.keepalive_loop()))
            
            # Echo receive task (if enabled)
            if self.echo_mode:
                tasks.append(asyncio.create_task(self.receive_loop()))
            
            # Key polling task
            if self.mode in ['iambic-a', 'iambic-b']:
                tasks.append(asyncio.create_task(self.poll_iambic_key()))
            else:
                tasks.append(asyncio.create_task(self.poll_straight_key()))
            
            # Wait for tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            print("\n\n✓ Stopped by user")
        finally:
            self.running = False
            self.connected = False
            
            # Print statistics
            if self.start_time:
                duration = time.time() - self.start_time
                print(f"\n--- Statistics ---")
                print(f"Duration: {duration:.1f}s")
                print(f"Events sent: {self.events_sent}")
                if self.echo_mode:
                    print(f"Events received: {self.events_received}")
                    if self.events_sent > 0:
                        print(f"Echo rate: {100*self.events_received/self.events_sent:.1f}%")
            
            # Cleanup
            if self.ws:
                await self.ws.close()
            if self.sidetone:
                self.sidetone.close()
            self.ser.close()


def main():
    parser = argparse.ArgumentParser(
        description='USB Key Sender for Web Platform (TCP-TS over WebSocket)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Straight key
  python3 cw_usb_key_sender_web.py --server wss://cw-relay.workers.dev --callsign SM5ABC
  
  # Iambic Mode B
  python3 cw_usb_key_sender_web.py --server wss://cw-relay.workers.dev --callsign SM5ABC --mode iambic-b --wpm 25
  
  # Echo mode testing
  python3 cw_usb_key_sender_web.py --server wss://cw-relay.workers.dev --callsign TEST --echo --debug
        """
    )
    
    parser.add_argument('--server', required=True,
                        help='WebSocket server URL (e.g., wss://cw-relay.workers.dev)')
    parser.add_argument('--callsign', required=True,
                        help='Your callsign')
    parser.add_argument('--room', default='main',
                        help='Room ID (default: main)')
    parser.add_argument('--port', default=None,
                        help='Serial port (auto-detected if not specified)')
    parser.add_argument('--mode', default='iambic-b',
                        choices=['straight', 'iambic-a', 'iambic-b'],
                        help='Keyer mode (default: iambic-b)')
    parser.add_argument('--wpm', type=int, default=20,
                        help='Keyer speed in WPM (default: 20)')
    parser.add_argument('--no-sidetone', action='store_true',
                        help='Disable sidetone audio')
    parser.add_argument('--echo', action='store_true',
                        help='Enable echo mode (receive back your events for testing)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    
    args = parser.parse_args()
    
    # Check audio availability
    if not args.no_sidetone and not AUDIO_AVAILABLE:
        print("\n⚠ Warning: pyaudio not available")
        print("  Install with: pip3 install pyaudio")
        print("  Continuing without sidetone...\n")
    
    # Create sender
    sender = USBKeyWebSender(
        server_url=args.server,
        callsign=args.callsign,
        room_id=args.room,
        serial_port=args.port,
        mode=args.mode,
        wpm=args.wpm,
        keyer_mode='B',  # Default to Mode B for iambic
        sidetone=not args.no_sidetone,
        echo_mode=args.echo,
        debug=args.debug
    )
    
    # Run
    try:
        asyncio.run(sender.run())
    except KeyboardInterrupt:
        print("\n✓ Goodbye!")


if __name__ == '__main__':
    main()
