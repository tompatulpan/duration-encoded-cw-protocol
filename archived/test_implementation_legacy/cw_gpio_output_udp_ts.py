#!/usr/bin/env python3
"""
CW GPIO Output UDP with Timestamps for Raspberry Pi

Receives CW packets with timestamps over UDP and controls GPIO pin for keying.
Uses timestamp-based scheduling for burst-resistant, consistent timing.

Usage:
    python3 cw_gpio_output_udp_ts.py [--pin PIN] [--active-low] [--buffer MS] [--port PORT] [--debug]

Example:
    python3 cw_gpio_output_udp_ts.py --pin 17 --buffer 100 --debug

GPIO Pin Configuration:
    - Default: BCM GPIO 17 (Physical pin 11)
    - Active-high by default (key down = GPIO HIGH)
    - Use --active-low for inverted logic

Protocol:
    - UDP port 7355 (UDP_PORT from cw_protocol_udp_ts)
    - Timestamp-based absolute scheduling
    - Best for LAN with low packet loss

Performance:
    - Queue depth: 2-3 events (burst-resistant)
    - Scheduling variance: ±1ms
    - Default buffer: 100ms (optimized for LAN/UDP)
"""

import socket
import sys
import time
import argparse
from cw_protocol_udp_ts import CWProtocolUDPTimestamp, UDP_PORT
from cw_receiver import GPIOKeyer, JitterBuffer


class CWGPIOOutputUDPTimestamp:
    """
    UDP timestamp-based CW receiver with GPIO output for Raspberry Pi.
    
    Manages UDP reception, timestamp synchronization, and GPIO keying
    with jitter buffer for consistent timing.
    """
    
    def __init__(self, port, gpio_pin, active_high, jitter_buffer_ms, debug):
        """
        Initialize GPIO output receiver with UDP timestamp protocol.
        
        Args:
            port: UDP port to listen on
            gpio_pin: BCM GPIO pin number
            active_high: True for active-high, False for active-low
            jitter_buffer_ms: Jitter buffer size in milliseconds
            debug: Enable debug output
        """
        self.port = port
        self.debug = debug
        
        # Initialize UDP timestamp protocol
        self.protocol = CWProtocolUDPTimestamp()
        
        # Initialize GPIO keyer
        print(f"[GPIO] Initializing BCM pin {gpio_pin} ({'active-high' if active_high else 'active-low'})")
        print(f"[GPIO] Key-down will be: {'HIGH' if active_high else 'LOW'}")
        self.gpio = GPIOKeyer(pin=gpio_pin, active_high=active_high)
        
        # Initialize jitter buffer
        print(f"[BUFFER] Jitter buffer: {jitter_buffer_ms}ms")
        self.jitter_buffer = JitterBuffer(buffer_ms=jitter_buffer_ms)
        self.jitter_buffer.debug = debug
        self.jitter_buffer.start(self._on_cw_event)
        
        # Connection state
        self.sender_timeline_offset = None
        
        print("[READY] GPIO output initialized, listening for UDP packets...")
    
    def _on_cw_event(self, key_down, duration_ms):
        """
        Callback invoked by jitter buffer at correct playout time.
        
        Args:
            key_down: True for key-down, False for key-up
            duration_ms: Duration in milliseconds (informational only)
        
        Note: Unlike audio which is continuous, GPIO is a discrete state.
        The jitter buffer will call this callback again with the opposite
        state at the correct time - no timer needed!
        """
        if self.debug:
            print(f"[GPIO] {'KEY DOWN' if key_down else 'KEY UP  '} for {duration_ms}ms (setting GPIO to {key_down})")
        
        # Simply set GPIO to new state
        # The jitter buffer ensures the next event arrives at the right time
        self.gpio.set_key_state(key_down)
    
    def run(self):
        """
        Main reception loop: bind, receive packets.
        
        Returns:
            Exit code (0 = success, 1 = error)
        """
        # Bind UDP socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('0.0.0.0', self.port))
            print(f"[UDP] Listening on port {self.port}")
        except Exception as e:
            print(f"[UDP] Failed to bind to port {self.port}: {e}")
            return 1
        
        packet_count = 0
        
        try:
            while True:
                # Receive UDP packet
                data, addr = sock.recvfrom(1024)
                arrival_time = time.time()
                
                # Parse packet
                result = self.protocol.parse_packet(data)
                
                if result is None:
                    # EOT or invalid packet
                    if self.debug:
                        print("[UDP] EOT or invalid packet received")
                    
                    # Reset state
                    self.gpio.set_key_state(False)
                    self.sender_timeline_offset = None
                    self.jitter_buffer.reset_connection()
                    packet_count = 0
                    continue
                
                key_down, duration_ms, timestamp_ms = result
                packet_count += 1
                
                # Synchronize to sender's timeline on first packet (per sender)
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
                
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Keyboard interrupt received")
            return 0
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            sock.close()
    
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
        description='CW GPIO Output UDP with Timestamps for Raspberry Pi',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 cw_gpio_output_udp_ts.py --pin 17 --buffer 100
  python3 cw_gpio_output_udp_ts.py --pin 18 --active-low --buffer 150 --debug

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
  LAN:      50-100ms  (low latency, low packet loss)
  WiFi:     100-150ms (recommended for UDP over WiFi)
  
Note: For Internet or high packet loss, use TCP version instead!

Protocol:
  UDP port 7355 (default)
  Timestamp-based absolute scheduling
  Queue depth: 2-3 events (burst-resistant)
  Scheduling variance: ±1ms
        """
    )
    
    parser.add_argument('--pin', type=int, default=17,
                        help='BCM GPIO pin number (default: 17)')
    parser.add_argument('--active-low', action='store_true',
                        help='Use active-low output (key-down = LOW)')
    parser.add_argument('--buffer', type=int, default=100,
                        help='Jitter buffer in ms (default: 100, recommended for UDP-TS)')
    parser.add_argument('--port', type=int, default=UDP_PORT,
                        help=f'UDP port (default: {UDP_PORT})')
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
    receiver = CWGPIOOutputUDPTimestamp(
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
