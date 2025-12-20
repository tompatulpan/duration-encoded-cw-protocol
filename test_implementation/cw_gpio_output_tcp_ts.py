#!/usr/bin/env python3
"""
CW GPIO Output TCP with Timestamps for Raspberry Pi

Receives CW packets with timestamps over TCP and controls GPIO pin for keying.
Uses timestamp-based scheduling for burst-resistant, consistent timing.

Usage:
    python3 cw_gpio_output_tcp_ts.py [--pin PIN] [--active-low] [--buffer MS] [--port PORT] [--debug]

Example:
    python3 cw_gpio_output_tcp_ts.py --pin 17 --buffer 150 --debug

GPIO Pin Configuration:
    - Default: BCM GPIO 17 (Physical pin 11)
    - Active-high by default (key down = GPIO HIGH)
    - Use --active-low for inverted logic

Protocol:
    - TCP port 7356 (TCP_PORT from cw_protocol_tcp_ts)
    - Length-prefix framing
    - Duration + timestamp fields
    - Timestamp-based absolute scheduling

Performance:
    - Queue depth: 2-3 events (vs 6-7 for duration-based)
    - Scheduling variance: ±1ms (vs ±50ms)
    - Default buffer: 150ms (optimized for WiFi/TCP)
"""

import socket
import sys
import time
import argparse
import threading
from cw_protocol_tcp_ts import CWProtocolTCPTimestamp, TCP_PORT
from cw_receiver import GPIOKeyer, JitterBuffer


class CWGPIOOutputTCPTimestamp:
    """
    TCP timestamp-based CW receiver with GPIO output for Raspberry Pi.
    
    Manages TCP connections, timestamp synchronization, and GPIO keying
    with jitter buffer for consistent timing under network conditions.
    """
    
    def __init__(self, port, gpio_pin, active_high, jitter_buffer_ms, debug):
        """
        Initialize GPIO output receiver with TCP timestamp protocol.
        
        Args:
            port: TCP port to listen on
            gpio_pin: BCM GPIO pin number
            active_high: True for active-high, False for active-low
            jitter_buffer_ms: Jitter buffer size in milliseconds
            debug: Enable debug output
        """
        self.port = port
        self.debug = debug
        
        # Initialize TCP timestamp protocol
        self.protocol = CWProtocolTCPTimestamp()
        
        # Initialize GPIO keyer
        print(f"[GPIO] Initializing BCM pin {gpio_pin} ({'active-high' if active_high else 'active-low'})")
        self.gpio = GPIOKeyer(pin=gpio_pin, active_high=active_high)
        
        # Initialize jitter buffer
        print(f"[BUFFER] Jitter buffer: {jitter_buffer_ms}ms")
        self.jitter_buffer = JitterBuffer(buffer_ms=jitter_buffer_ms)
        self.jitter_buffer.debug = debug
        self.jitter_buffer.start(self._on_cw_event)
        
        # Connection state
        self.sender_timeline_offset = None
        
        print("[READY] GPIO output initialized, waiting for connections...")
    
    def _on_cw_event(self, key_down, duration_ms):
        """
        Callback invoked by jitter buffer at correct playout time.
        
        Args:
            key_down: True for key-down, False for key-up
            duration_ms: Duration of this state in milliseconds
        """
        # Set GPIO state immediately
        self.gpio.set_key_state(key_down)
        
        if self.debug:
            print(f"[GPIO] {'DOWN' if key_down else 'UP'} for {duration_ms}ms")
        
        # If key down, schedule automatic key-up after duration
        if key_down:
            def release_key():
                self.gpio.set_key_state(False)
                if self.debug:
                    print(f"[GPIO] Auto-release after {duration_ms}ms")
            
            timer = threading.Timer(duration_ms / 1000.0, release_key)
            timer.daemon = True
            timer.start()
    
    def run(self):
        """
        Main connection loop: listen, accept, receive packets.
        
        Returns:
            Exit code (0 = success, 1 = error)
        """
        # Start TCP server
        print(f"[TCP] Starting server on port {self.port}...")
        if not self.protocol.listen(self.port):
            print(f"[TCP] Failed to start server on port {self.port}")
            return 1
        
        print(f"[TCP] Listening on port {self.port}")
        
        try:
            while True:
                # Wait for incoming connection
                print("[TCP] Waiting for connection...")
                addr = self.protocol.accept()
                
                if not addr:
                    print("[TCP] Accept failed, retrying...")
                    time.sleep(1.0)
                    continue
                
                print(f"[TCP] Connected from {addr[0]}:{addr[1]}")
                
                # Reset state for new connection
                self.gpio.set_key_state(False)  # Ensure key UP
                self.sender_timeline_offset = None
                self.jitter_buffer.reset_connection()
                
                # Receive packets from this connection
                packet_count = 0
                while self.protocol.connected:
                    result = self.protocol.recv_packet()
                    
                    if result is None:
                        # EOT or disconnect
                        print("[TCP] End of transmission or connection closed")
                        break
                    
                    key_down, duration_ms, timestamp_ms = result
                    packet_count += 1
                    
                    # Synchronize to sender's timeline on first packet
                    if self.sender_timeline_offset is None:
                        self.sender_timeline_offset = time.time() - (timestamp_ms / 1000.0)
                        if self.debug:
                            print(f"[SYNC] Timeline synchronized (offset: {self.sender_timeline_offset:.3f})")
                    
                    # Calculate sender's event time (absolute reference)
                    sender_event_time = self.sender_timeline_offset + (timestamp_ms / 1000.0)
                    
                    if self.debug:
                        now = time.time()
                        event_delay = (sender_event_time - now) * 1000.0
                        print(f"[RX] Packet {packet_count}: {'DOWN' if key_down else 'UP'} {duration_ms}ms, "
                              f"ts={timestamp_ms}ms, delay={event_delay:.1f}ms")
                    
                    # Add to jitter buffer (timestamp-based scheduling)
                    self.jitter_buffer.add_event_ts(key_down, duration_ms, sender_event_time)
                
                # Connection ended
                print(f"[TCP] Connection closed ({packet_count} packets received)")
                self.gpio.set_key_state(False)  # Force key UP
                
                # Drain jitter buffer before accepting new connection
                print("[BUFFER] Draining buffer...")
                self.jitter_buffer.drain_buffer()
                
                # Reset timeline offset for next connection
                self.sender_timeline_offset = None
                
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Keyboard interrupt received")
            return 0
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    def cleanup(self):
        """Clean up resources on exit."""
        print("[CLEANUP] Shutting down...")
        self.jitter_buffer.stop()
        self.gpio.cleanup()
        self.protocol.close()
        print("[CLEANUP] Complete")


def main():
    """Parse arguments and run GPIO output receiver."""
    parser = argparse.ArgumentParser(
        description='CW GPIO Output TCP with Timestamps for Raspberry Pi',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 cw_gpio_output_tcp_ts.py --pin 17 --buffer 150
  python3 cw_gpio_output_tcp_ts.py --pin 18 --active-low --buffer 200 --debug

GPIO Pin Numbering:
  Uses BCM pin numbering (not physical pin numbers)
  Default: GPIO 17 = Physical pin 11
  
  Common BCM pins:
    GPIO 17 = Physical pin 11
    GPIO 27 = Physical pin 13
    GPIO 22 = Physical pin 15
    GPIO 23 = Physical pin 16
    GPIO 24 = Physical pin 18

Buffer Sizing:
  LAN:      50-100ms  (low latency)
  WiFi:     150ms     (recommended, handles bursts)
  Internet: 150-200ms (handles jitter)
  Poor:     200-300ms (high packet delay variation)

Protocol:
  TCP port 7356 (default)
  Timestamp-based absolute scheduling
  Queue depth: 2-3 events (burst-resistant)
  Scheduling variance: ±1ms
        """
    )
    
    parser.add_argument('--pin', type=int, default=17,
                        help='BCM GPIO pin number (default: 17)')
    parser.add_argument('--active-low', action='store_true',
                        help='Use active-low output (key-down = LOW)')
    parser.add_argument('--buffer', type=int, default=150,
                        help='Jitter buffer in ms (default: 150, recommended for TCP-TS)')
    parser.add_argument('--port', type=int, default=TCP_PORT,
                        help=f'TCP port (default: {TCP_PORT})')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.pin < 0 or args.pin > 27:
        print(f"[ERROR] Invalid GPIO pin: {args.pin} (valid range: 0-27)")
        return 1
    
    if args.buffer < 0:
        print(f"[ERROR] Invalid buffer size: {args.buffer}ms (must be >= 0)")
        return 1
    
    if args.port < 1024 or args.port > 65535:
        print(f"[ERROR] Invalid port: {args.port} (valid range: 1024-65535)")
        return 1
    
    # Create and run receiver
    receiver = CWGPIOOutputTCPTimestamp(
        port=args.port,
        gpio_pin=args.pin,
        active_high=not args.active_low,
        jitter_buffer_ms=args.buffer,
        debug=args.debug
    )
    
    try:
        exit_code = receiver.run()
    finally:
        receiver.cleanup()
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
