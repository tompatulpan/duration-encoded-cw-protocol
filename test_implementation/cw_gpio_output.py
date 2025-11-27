#!/usr/bin/env python3
"""
CW GPIO Output for Raspberry Pi - Drive key relay/transistor via GPIO

This module receives CW packets over UDP and outputs key-down/key-up
signals via a Raspberry Pi GPIO pin. Suitable for driving:
- Relay (for vintage transmitters)
- Transistor/MOSFET (for modern rigs)
- Opto-isolator (for isolation)

Pin Configuration (BCM numbering):
- GPIO 17 (Pin 11) - Key output (default)
- GND (Pin 6 or 9) - Common ground

Hardware Setup:
1. Relay: Connect relay coil between GPIO and GND (with flyback diode)
2. Transistor: Use GPIO to control NPN/MOSFET gate/base
3. Opto-isolator: Connect LED side to GPIO (with current-limiting resistor)

Usage:
    python3 cw_gpio_output.py --pin 17 --buffer 100

Requirements:
    sudo apt install -y python3-rpi.gpio
    or
    pip3 install RPi.GPIO
"""

import socket
import sys
import time
import threading
import queue
import argparse
from cw_protocol import CWProtocol, UDP_PORT

# GPIO support (Raspberry Pi)
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("ERROR: RPi.GPIO not available")
    print("Install with: sudo apt install -y python3-rpi.gpio")
    print("or: pip3 install RPi.GPIO")
    sys.exit(1)


class GPIOKeyer:
    """Output CW keying via Raspberry Pi GPIO pin"""
    
    def __init__(self, pin=17, active_high=True):
        """
        Initialize GPIO output
        
        Args:
            pin: BCM GPIO pin number (default 17 = physical pin 11)
            active_high: True = key-down is HIGH, False = key-down is LOW
        """
        self.pin = pin
        self.active_high = active_high
        self.key_down = False
        
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
        GPIO.setwarnings(False)
        GPIO.setup(self.pin, GPIO.OUT)
        
        # Initialize to key-up state
        self.set_key_state(False)
        
        print(f"GPIO keyer initialized on BCM pin {self.pin}")
        print(f"Key-down = {'HIGH' if active_high else 'LOW'}")
    
    def set_key_state(self, key_down):
        """Set key state (True = down/transmit, False = up/idle)"""
        self.key_down = key_down
        
        if self.active_high:
            GPIO.output(self.pin, GPIO.HIGH if key_down else GPIO.LOW)
        else:
            GPIO.output(self.pin, GPIO.LOW if key_down else GPIO.HIGH)
    
    def cleanup(self):
        """Release GPIO resources"""
        self.set_key_state(False)  # Ensure key is up
        GPIO.cleanup()


class JitterBuffer:
    """Buffer CW events to smooth out network jitter"""
    
    def __init__(self, buffer_ms=100):
        """
        Initialize jitter buffer with RELATIVE timing
        
        Args:
            buffer_ms: Buffer depth in milliseconds (recommended: 50-200ms)
        """
        self.buffer_ms = buffer_ms
        self.event_queue = queue.PriorityQueue()
        self.running = False
        self.callback = None
        self.last_event_end_time = None  # When previous event finishes
        self.last_arrival = None
        
        # Statistics tracking
        self.stats_delays = []
        self.stats_shifts = 0
        self.stats_max_queue = 0
        
        # State validation
        self.expected_key_state = None
        self.state_errors = 0
        
        # Debug mode
        self.debug = False
        
    def add_event(self, key_down, duration_ms, arrival_time):
        """Add event to buffer using RELATIVE timing to preserve tempo"""
        
        # Validate state transition
        if self.expected_key_state is not None and key_down == self.expected_key_state:
            self.state_errors += 1
            print(f"\n[ERROR] Invalid state: got {'DOWN' if key_down else 'UP'} twice in a row (error #{self.state_errors})")
        self.expected_key_state = key_down
        
        # Reset if there's a long gap (>2 seconds)
        if self.last_arrival and (arrival_time - self.last_arrival) > 2.0:
            self.last_event_end_time = None
            while not self.event_queue.empty():
                try:
                    self.event_queue.get_nowait()
                except queue.Empty:
                    break
        
        # Calculate playout time using RELATIVE timing
        now = time.time()
        
        if self.last_event_end_time is None:
            # First event: schedule buffer_ms from now
            playout_time = now + self.buffer_ms / 1000.0
        else:
            # Subsequent events: start when previous event finished
            playout_time = self.last_event_end_time
        
        # ADAPTIVE: If event would be late, shift it forward
        if playout_time < now:
            lateness = (now - playout_time) * 1000
            playout_time = now
            self.stats_shifts += 1
            if self.debug:
                print(f"[WARN] Event was {lateness:.1f}ms late, shifting forward")
        
        # Calculate when event ends
        event_end_time = playout_time + duration_ms / 1000.0
        
        # Queue event
        self.event_queue.put((playout_time, key_down, duration_ms))
        
        # Track delay
        delay = (playout_time - arrival_time) * 1000
        self.stats_delays.append(delay)
        if len(self.stats_delays) > 1000:
            self.stats_delays.pop(0)
        
        # Update state
        self.last_event_end_time = event_end_time
        self.last_arrival = arrival_time
        
        # Track max queue depth
        qsize = self.event_queue.qsize()
        if qsize > self.stats_max_queue:
            self.stats_max_queue = qsize
    
    def set_callback(self, callback):
        """Set callback function(key_down, duration_ms)"""
        self.callback = callback
    
    def start(self):
        """Start buffer processing thread"""
        self.running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop buffer processing"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join()
    
    def _process_loop(self):
        """Process buffered events and trigger output at correct time"""
        while self.running:
            try:
                # Get next event (blocking with timeout)
                playout_time, key_down, duration_ms = self.event_queue.get(timeout=0.1)
                
                # Wait until playout time
                now = time.time()
                wait_time = playout_time - now
                if wait_time > 0:
                    time.sleep(wait_time)
                
                # Trigger output via callback
                if self.callback:
                    self.callback(key_down, duration_ms)
                
            except queue.Empty:
                continue
    
    def get_stats(self):
        """Return buffer statistics"""
        if not self.stats_delays:
            return None
        
        return {
            'count': len(self.stats_delays),
            'delay_avg': sum(self.stats_delays) / len(self.stats_delays),
            'delay_min': min(self.stats_delays),
            'delay_max': max(self.stats_delays),
            'shifts': self.stats_shifts,
            'max_queue': self.stats_max_queue,
            'state_errors': self.state_errors
        }


def main():
    parser = argparse.ArgumentParser(description='CW GPIO Output for Raspberry Pi')
    parser.add_argument('--pin', type=int, default=17,
                        help='BCM GPIO pin number (default: 17 = physical pin 11)')
    parser.add_argument('--active-low', action='store_true',
                        help='Use active-low output (key-down = LOW)')
    parser.add_argument('--buffer', type=int, default=100,
                        help='Jitter buffer size in milliseconds (default: 100)')
    parser.add_argument('--port', type=int, default=UDP_PORT,
                        help=f'UDP port to listen on (default: {UDP_PORT})')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    parser.add_argument('--stats', action='store_true',
                        help='Show periodic statistics')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW GPIO Output for Raspberry Pi")
    print("=" * 60)
    print(f"GPIO Pin: BCM {args.pin} (physical pin {_bcm_to_physical(args.pin)})")
    print(f"Active: {'LOW' if args.active_low else 'HIGH'}")
    print(f"Buffer: {args.buffer}ms")
    print(f"UDP Port: {args.port}")
    print("=" * 60)
    print("\nHardware Setup:")
    print(f"  GPIO {args.pin} --> Relay/Transistor/Opto")
    print(f"  GND (Pin 6) --> Common ground")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)
    
    # Initialize GPIO keyer
    gpio = GPIOKeyer(pin=args.pin, active_high=not args.active_low)
    
    # Initialize jitter buffer
    jitter_buffer = JitterBuffer(buffer_ms=args.buffer)
    jitter_buffer.debug = args.debug
    
    # Define output callback
    def on_cw_event(key_down, duration_ms):
        """Called when event should be output"""
        gpio.set_key_state(key_down)
        
        # Auto-schedule key-up after duration
        if key_down:
            threading.Timer(duration_ms / 1000.0, lambda: gpio.set_key_state(False)).start()
        
        if args.debug:
            print(f"{'KEY DOWN' if key_down else 'KEY UP  '} for {duration_ms}ms")
    
    jitter_buffer.set_callback(on_cw_event)
    jitter_buffer.start()
    
    # Setup UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', args.port))
    
    protocol = CWProtocol()
    last_stats_time = time.time()
    
    print(f"\nListening on UDP port {args.port}...")
    
    try:
        while True:
            data, addr = sock.recvfrom(1024)
            arrival_time = time.time()
            
            # Parse packet
            result = protocol.parse_packet(data)
            if result and result['events']:
                for key_down, duration_ms in result['events']:
                    jitter_buffer.add_event(key_down, duration_ms, arrival_time)
            
            # Print stats periodically
            if args.stats and time.time() - last_stats_time > 10.0:
                stats = jitter_buffer.get_stats()
                if stats:
                    print(f"\n[STATS] Packets: {stats['count']}, "
                          f"Delay: {stats['delay_avg']:.1f}ms (min={stats['delay_min']:.1f}, max={stats['delay_max']:.1f}), "
                          f"Shifts: {stats['shifts']}, "
                          f"Errors: {stats['state_errors']}")
                last_stats_time = time.time()
    
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    
    finally:
        jitter_buffer.stop()
        gpio.cleanup()
        sock.close()
        print("GPIO cleaned up. 73!")


def _bcm_to_physical(bcm_pin):
    """Convert BCM pin number to physical pin number"""
    bcm_to_phys = {
        17: 11, 27: 13, 22: 15, 23: 16, 24: 18, 25: 22,
        5: 29, 6: 31, 12: 32, 13: 33, 19: 35, 16: 36, 26: 37, 20: 38, 21: 40
    }
    return bcm_to_phys.get(bcm_pin, "?")


if __name__ == '__main__':
    main()
