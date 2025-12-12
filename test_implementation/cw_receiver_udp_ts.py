#!/usr/bin/env python3
"""
CW Receiver UDP with Timestamps
Receives UDP packets with timestamps and plays sidetone with jitter buffer
"""

import argparse
import time
from cw_protocol_udp_ts import CWProtocolUDPTimestamp, UDP_TS_PORT
from cw_receiver import JitterBuffer, SidetoneGenerator


class CWReceiverUDPTimestamp:
    """CW receiver for UDP timestamp protocol"""
    
    def __init__(self, port=UDP_TS_PORT, jitter_buffer_ms=0, audio_enabled=True, debug=False, debug_packets=False):
        self.port = port
        self.protocol = CWProtocolUDPTimestamp()
        self.jitter_buffer_ms = jitter_buffer_ms
        self.audio_enabled = audio_enabled
        self.debug = debug
        self.debug_packets = debug_packets
        
        # Timing statistics
        self.events_received = 0
        self.max_delay_ms = 0
        self.sender_timeline_offset = None  # Synchronize to sender timeline
        
        # Jitter buffer for timestamp protocol
        self.jitter_buffer = None
        if jitter_buffer_ms > 0:
            self.jitter_buffer = JitterBuffer(jitter_buffer_ms)
        
        # Audio output
        self.sidetone = None
        if audio_enabled:
            self.sidetone = SidetoneGenerator(frequency=700)  # RX frequency
        
        # State tracking
        self.last_key_state = False
        self.state_errors = 0
        self.suppress_state_errors = False
        self.last_arrival_time = None
        
    def _playout_callback(self, key_down, duration_ms):
        """Callback for jitter buffer playout"""
        if self.audio_enabled and self.sidetone:
            self.sidetone.set_key(key_down)
        
        if self.debug:
            state_str = "DOWN" if key_down else "UP"
            print(f"[PLAY] {state_str} {duration_ms}ms")
    
    def _immediate_playout(self, key_down, duration_ms):
        """Play immediately without jitter buffer"""
        if self.audio_enabled and self.sidetone:
            self.sidetone.set_key(key_down)
        
        if self.debug:
            state_str = "DOWN" if key_down else "UP"
            print(f"[PLAY] {state_str} {duration_ms}ms")
    
    def run(self):
        """Main receiver loop"""
        # Create socket
        print(f"Starting CW Receiver UDP Timestamp on port {self.port}")
        if self.jitter_buffer_ms > 0:
            print(f"Jitter buffer: {self.jitter_buffer_ms}ms (timestamp-based absolute scheduling)")
            self.jitter_buffer.start(self._playout_callback)
        else:
            print("Jitter buffer: disabled (immediate playout)")
        
        if not self.audio_enabled:
            print("Audio: disabled")
        
        self.protocol.create_socket(self.port)
        self.protocol.sock.settimeout(0.1)  # 100ms timeout for clean shutdown
        
        try:
            while True:
                result = self.protocol.recv_packet()
                
                if result is None:
                    continue
                
                key_down, duration_ms, timestamp_ms, sender_addr = result
                
                # Check for EOT
                if key_down == 'EOT':
                    print("\n[EOT] End-of-transmission received")
                    # Reset state for next transmission
                    self.last_key_state = False
                    self.sender_timeline_offset = None
                    self.suppress_state_errors = False
                    continue
                
                now = time.time()
                
                # Track arrival timing
                arrival_gap = 0
                if self.last_arrival_time:
                    arrival_gap = now - self.last_arrival_time
                self.last_arrival_time = now
                
                # Debug packet info
                if self.debug_packets:
                    state_str = "DOWN" if key_down else "UP"
                    print(f"[RECV] {state_str} {duration_ms}ms, timestamp={timestamp_ms}ms, gap={arrival_gap*1000:.1f}ms")
                
                # Validate state transitions
                if key_down == self.last_key_state:
                    self.state_errors += 1
                    if not self.suppress_state_errors:
                        state_str = "DOWN" if key_down else "UP"
                        print(f"[ERROR] Invalid state: got {state_str} twice in a row (total errors: {self.state_errors})")
                        if self.state_errors >= 5:
                            print("[WARNING] Many state errors - suppressing further warnings")
                            self.suppress_state_errors = True
                
                self.last_key_state = key_down
                
                # Synchronize to sender timeline on first packet
                if self.sender_timeline_offset is None:
                    self.sender_timeline_offset = now - (timestamp_ms / 1000.0)
                    if self.debug:
                        print(f"[SYNC] Synchronized to sender timeline (offset={self.sender_timeline_offset:.3f})")
                
                # Calculate absolute playout time
                sender_event_time = self.sender_timeline_offset + (timestamp_ms / 1000.0)
                
                if self.jitter_buffer:
                    # Timestamp-based absolute scheduling
                    playout_time = sender_event_time + (self.jitter_buffer_ms / 1000.0)
                    
                    # Calculate delay
                    delay_ms = (playout_time - now) * 1000
                    
                    if self.debug:
                        state_str = "DOWN" if key_down else "UP"
                        print(f"[SCHEDULE] {state_str} {duration_ms}ms, timestamp={timestamp_ms}ms, delay={delay_ms:.1f}ms")
                    
                    # Schedule in jitter buffer
                    self.jitter_buffer.add_event(key_down, duration_ms, playout_time)
                    
                    # Track max delay
                    if delay_ms > self.max_delay_ms:
                        self.max_delay_ms = delay_ms
                
                else:
                    # Immediate playout (no buffer)
                    self._immediate_playout(key_down, duration_ms)
                
                # Update statistics
                self.events_received += 1
        
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        
        finally:
            # Print statistics
            print("\n" + "="*50)
            print("Reception Statistics:")
            print("="*50)
            print(f"Events received:  {self.events_received}")
            print(f"Packets received: {self.protocol.packets_received}")
            print(f"Packets lost:     {self.protocol.packets_lost}")
            print(f"State errors:     {self.state_errors}")
            
            if self.max_delay_ms > 0:
                print(f"\nMax delay seen:   {self.max_delay_ms:.1f}ms")
                
                if self.jitter_buffer_ms > 0:
                    headroom = self.jitter_buffer_ms - self.max_delay_ms
                    print(f"Buffer headroom:  {headroom:.1f}ms")
                    
                    if headroom > self.jitter_buffer_ms * 0.5:
                        print("Buffer larger than needed - consider reducing")
                    elif headroom < self.jitter_buffer_ms * 0.1:
                        print("Buffer close to limit - consider increasing")
                    else:
                        print("Buffer size optimal")
            
            # Cleanup
            if self.jitter_buffer:
                print("\nDraining jitter buffer...")
                time.sleep(1.0)  # Allow buffer to drain
                self.jitter_buffer.stop()
            
            if self.sidetone:
                self.sidetone.close()
            
            self.protocol.close()
            print("Receiver stopped.")


def main():
    parser = argparse.ArgumentParser(description='CW Receiver UDP with Timestamps')
    parser.add_argument('--port', type=int, default=UDP_TS_PORT,
                       help=f'UDP port to listen on (default: {UDP_TS_PORT})')
    parser.add_argument('--jitter-buffer', type=int, default=0,
                       help='Jitter buffer size in milliseconds (0=disabled, recommended: 100-150 for WiFi)')
    parser.add_argument('--no-audio', action='store_true',
                       help='Disable audio output (testing mode)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug output')
    parser.add_argument('--debug-packets', action='store_true',
                       help='Show every packet received')
    
    args = parser.parse_args()
    
    receiver = CWReceiverUDPTimestamp(
        port=args.port,
        jitter_buffer_ms=args.jitter_buffer,
        audio_enabled=not args.no_audio,
        debug=args.debug,
        debug_packets=args.debug_packets
    )
    
    receiver.run()


if __name__ == '__main__':
    main()
