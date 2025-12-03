#!/usr/bin/env python3
"""
CW Studio Client with Sidetone - Send CW events to server with local audio feedback
"""
import sys
import os
import json
import asyncio
import websockets
import threading
import numpy as np

# Import from parent directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cw_usb_key_sender_with_decoder import IambicKeyer
import serial
import time

# Try to import audio library
try:
    import pyaudio
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("⚠ pyaudio not installed - no sidetone available")
    print("  Install with: pip3 install pyaudio")


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
        self.playing = False
        self.phase = 0.0
        
        # Initialize PyAudio
        try:
            self.p = pyaudio.PyAudio()
            self.stream = self.p.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=512,
                stream_callback=self._audio_callback
            )
            self.stream.start_stream()
            print(f"✓ Sidetone initialized ({frequency}Hz)")
        except Exception as e:
            print(f"✗ Sidetone failed: {e}")
            self.enabled = False
            if hasattr(self, 'p'):
                self.p.terminate()
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Generate audio samples - matches working implementation"""
        if self.playing:
            # Generate sine wave (same method as working version)
            samples = np.arange(frame_count)
            omega = 2.0 * np.pi * self.frequency / self.sample_rate
            audio = self.volume * np.sin(omega * samples + self.phase).astype(np.float32)
            self.phase = (self.phase + omega * frame_count) % (2.0 * np.pi)
        else:
            # Silence
            audio = np.zeros(frame_count, dtype=np.float32)
        
        return (audio.tobytes(), pyaudio.paContinue)
    
    def start(self):
        """Start playing tone"""
        if self.enabled:
            self.playing = True
    
    def stop(self):
        """Stop playing tone"""
        if self.enabled:
            self.playing = False
    
    def close(self):
        """Cleanup audio resources"""
        if self.enabled:
            self.stream.stop_stream()
            self.stream.close()
            self.p.terminate()


class CWStudioClient:
    def __init__(self, server_url, room_id, callsign, serial_port, mode='iambic', wpm=20, keyer_mode='B', sidetone=True):
        self.server_url = server_url
        self.room_id = room_id
        self.callsign = callsign
        self.serial_port = serial_port
        self.mode = mode
        self.wpm = wpm
        self.keyer_mode = keyer_mode
        self.ws = None
        self.peer_id = f"{callsign}_{int(time.time())}"
        
        # Setup sidetone
        self.sidetone = SidetoneGenerator() if sidetone and AUDIO_AVAILABLE else None
        
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
                'callsign': self.callsign
            }
            await self.ws.send(json.dumps(join_msg))
            print(f"✓ Connected as {self.callsign}")
            
            # Wait for join confirmation
            response = await self.ws.recv()
            data = json.loads(response)
            if data.get('type') == 'joined':
                print(f"✓ Joined room '{self.room_id}'")
            
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            sys.exit(1)
    
    async def send_cw_event(self, event_type, duration_ms=0):
        """Send CW event to server"""
        if self.ws:
            try:
                msg = {
                    'type': 'cw_event',
                    'peerId': self.peer_id,
                    'callsign': self.callsign,
                    'event': event_type,
                    'duration': duration_ms,
                    'timestamp': int(time.time() * 1000)
                }
                await self.ws.send(json.dumps(msg))
                # Note: Sidetone is now controlled in the keyer callback for proper timing
                        
            except Exception as e:
                print(f"\n✗ Failed to send event: {e}")
    
    async def poll_iambic(self):
        """Poll iambic paddles and send events"""
        print("✓ Iambic keyer ready")
        
        # Create a callback to send events
        def send_element(key_down, duration_ms):
            """Callback for keyer to send events (runs synchronously during keyer update)"""
            # Control sidetone immediately when keyer generates the element
            if self.sidetone:
                if key_down:
                    self.sidetone.start()
                else:
                    self.sidetone.stop()
            
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
                # Read key state (CTS = key down for straight key)
                current_state = self.ser.cts
                
                if current_state and not key_down:
                    # Key pressed
                    key_down = True
                    key_down_time = time.time()
                    
                    # Control sidetone immediately
                    if self.sidetone:
                        self.sidetone.start()
                    
                    await self.send_cw_event('tone_start', 0)
                    print("▄", end='', flush=True)
                    
                elif not current_state and key_down:
                    # Key released
                    key_down = False
                    duration_ms = int((time.time() - key_down_time) * 1000)
                    
                    # Control sidetone immediately
                    if self.sidetone:
                        self.sidetone.stop()
                    
                    await self.send_cw_event('tone_end', duration_ms)
                    print("▀", end='', flush=True)
                
                # Small sleep to prevent busy loop
                await asyncio.sleep(0.001)
                    
            except Exception as e:
                print(f"\n✗ Polling error: {e}")
                break
    
    async def run(self):
        """Main run loop"""
        await self.connect()
        
        # Start polling based on mode
        if self.mode == 'iambic':
            await self.poll_iambic()
        else:  # straight key
            await self.poll_straight()
    
    def cleanup(self):
        """Cleanup resources"""
        if self.sidetone:
            self.sidetone.close()
        if self.ser:
            self.ser.close()


def main():
    if len(sys.argv) < 6:
        print("CW Studio Client with Sidetone")
        print("=" * 60)
        print("Usage:")
        print("  python3 cw_studio_client_with_sidetone.py <server_url> <room_id> <callsign> <mode> <wpm> <port> [--no-sidetone]")
        print()
        print("Parameters:")
        print("  server_url  : WebSocket URL (e.g., wss://cw-studio-signaling.data4-9de.workers.dev/ws)")
        print("  room_id     : Room to join (e.g., main)")
        print("  callsign    : Your callsign (e.g., SM0ONR)")
        print("  mode        : iambic-a, iambic-b, or straight")
        print("  wpm         : Speed in WPM (e.g., 25)")
        print("  port        : Serial port (e.g., /dev/ttyUSB0)")
        print("  --no-sidetone : Disable local sidetone (optional)")
        print()
        print("Examples:")
        print("  # With sidetone")
        print("  python3 cw_studio_client_with_sidetone.py wss://cw-studio-signaling.data4-9de.workers.dev/ws \\")
        print("      main SM0ONR iambic-b 25 /dev/ttyUSB0")
        print()
        print("  # Without sidetone")
        print("  python3 cw_studio_client_with_sidetone.py wss://cw-studio-signaling.data4-9de.workers.dev/ws \\")
        print("      main SM0ONR iambic-b 25 /dev/ttyUSB0 --no-sidetone")
        sys.exit(1)
    
    server_url = sys.argv[1]
    room_id = sys.argv[2]
    callsign = sys.argv[3]
    mode_str = sys.argv[4]
    wpm = int(sys.argv[5])
    port = sys.argv[6]
    
    # Check for --no-sidetone flag
    sidetone_enabled = '--no-sidetone' not in sys.argv
    
    # Parse mode
    if mode_str == 'straight':
        mode = 'straight'
        keyer_mode = None
    elif mode_str == 'iambic-a':
        mode = 'iambic'
        keyer_mode = 'A'
    elif mode_str == 'iambic-b':
        mode = 'iambic'
        keyer_mode = 'B'
    else:
        print(f"✗ Invalid mode: {mode_str}")
        print("  Valid modes: straight, iambic-a, iambic-b")
        sys.exit(1)
    
    print(f"CW Studio Client - {callsign}")
    print(f"Mode: {mode_str}, WPM: {wpm}, Port: {port}")
    print(f"Sidetone: {'enabled' if sidetone_enabled else 'disabled'}")
    print("=" * 60)
    
    # Create and run client
    client = CWStudioClient(
        server_url, room_id, callsign, port, 
        mode=mode, wpm=wpm, keyer_mode=keyer_mode,
        sidetone=sidetone_enabled
    )
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n\n✓ Disconnected")
    finally:
        client.cleanup()


if __name__ == '__main__':
    main()
