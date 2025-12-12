#!/usr/bin/env python3
"""
CW GPIO Output with FEC for Raspberry Pi - Drive key relay/transistor via GPIO

This module receives CW packets with FEC over UDP and outputs key-down/key-up
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
    python3 cw_gpio_output_fec.py --pin 17 --buffer 200

Requirements:
    sudo apt install -y python3-rpi.gpio
    pip3 install reedsolo
    or
    pip3 install RPi.GPIO reedsolo
"""

import socket
import sys
import time
import threading
import queue
import argparse
from cw_protocol_fec import CWProtocolFEC, FECDecoder, UDP_PORT

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


# Import JitterBuffer from standard GPIO output (reuse existing code)
from cw_gpio_output import GPIOKeyer, JitterBuffer


class CWGPIOOutputFEC:
    """CW GPIO Output with FEC support"""
    
    def __init__(self, port=UDP_PORT, gpio_pin=17, active_high=True, jitter_buffer_ms=200, debug=False):
        self.port = port
        self.jitter_buffer_ms = jitter_buffer_ms
        self.debug = debug
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Increase UDP receive buffer
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)
        except:
            pass
        
        self.socket.bind(('0.0.0.0', port))
        
        self.protocol = CWProtocolFEC()
        
        # FEC decoder
        self.fec_decoder = FECDecoder()
        
        # GPIO keyer
        self.gpio = GPIOKeyer(pin=gpio_pin, active_high=active_high)
        
        # Jitter buffer
        self.jitter_buffer = None
        if jitter_buffer_ms > 0:
            self.jitter_buffer = JitterBuffer(buffer_ms=jitter_buffer_ms)
            self.jitter_buffer.debug = debug
            self.jitter_buffer.set_callback(self._on_cw_event)
            self.jitter_buffer.start()
        
        # Track processed sequences
        self.processed_sequences = set()
        self.last_sequence_cleanup = time.time()
        
        # Statistics
        self.total_packets = 0
        self.fec_packets = 0
        self.data_packets = 0
        self.recovered_packets = 0
        self.duplicate_packets = 0
    
    def _on_cw_event(self, key_down, duration_ms):
        """Called when event should be output to GPIO"""
        self.gpio.set_key_state(key_down)
        
        # Auto-schedule key-up after duration
        if key_down:
            threading.Timer(duration_ms / 1000.0, lambda: self.gpio.set_key_state(False)).start()
        
        if self.debug:
            print(f"{'KEY DOWN' if key_down else 'KEY UP  '} for {duration_ms}ms")
    
    def _process_packet(self, data, arrival_time):
        """Process a received packet (data or FEC)"""
        self.total_packets += 1
        
        # Parse packet
        parsed = self.protocol.parse_packet_fec(data)
        if not parsed:
            return
        
        # Check if this is an EOT packet
        if len(data) == 3:  # EOT packet
            if self.debug:
                print("[EOT] End of transmission")
            
            # Flush incomplete blocks
            incomplete_packets = self.fec_decoder.flush_incomplete_blocks()
            if incomplete_packets:
                if self.debug:
                    print(f"[FEC] Flushed {len(incomplete_packets)} packets from incomplete blocks")
                
                # Reset state tracking and suppress validation errors for flushed packets
                if self.jitter_buffer:
                    self.jitter_buffer.expected_key_state = None
                    self.jitter_buffer.suppress_state_errors = True
                
                for pkt in incomplete_packets:
                    if pkt['sequence'] not in self.processed_sequences:
                        self._output_events(pkt, arrival_time, from_incomplete=True)
                        self.processed_sequences.add(pkt['sequence'])
                
                # Re-enable state validation
                if self.jitter_buffer:
                    self.jitter_buffer.suppress_state_errors = False
            
            # Reset FEC decoder for next transmission
            self.fec_decoder.reset()
            return
        
        # Track packet type
        fec_info = parsed.get('fec_info')
        if fec_info:
            if fec_info['is_fec']:
                self.fec_packets += 1
            else:
                self.data_packets += 1
        
        # Add to FEC decoder
        complete_block = self.fec_decoder.add_packet(data, parsed)
        
        if complete_block:
            # Process all packets in the complete block
            recovered_count = 0
            for packet in complete_block:
                seq = packet['sequence']
                
                # Check for duplicates
                if seq in self.processed_sequences:
                    self.duplicate_packets += 1
                    continue
                
                self.processed_sequences.add(seq)
                
                # Track if this was recovered
                if packet.get('recovered', False):
                    recovered_count += 1
                    self.recovered_packets += 1
                
                # Output events
                self._output_events(packet, arrival_time, recovered=packet.get('recovered', False))
            
            if self.debug and recovered_count > 0:
                print(f"[FEC] Recovered {recovered_count} lost packets")
            
            # Check if block had gaps - suppress state validation temporarily
            if complete_block and complete_block[0].get('had_gaps', False):
                if self.jitter_buffer:
                    self.jitter_buffer.expected_key_state = None
                    if self.debug:
                        print("[FEC] Block had gaps, reset state tracking")
        
        # Cleanup old sequence numbers periodically (keep last 10 seconds)
        if time.time() - self.last_sequence_cleanup > 10.0:
            # Keep only recent sequences (arbitrary 1000 most recent)
            if len(self.processed_sequences) > 1000:
                sorted_seqs = sorted(self.processed_sequences)
                self.processed_sequences = set(sorted_seqs[-1000:])
            self.last_sequence_cleanup = time.time()
    
    def _output_events(self, packet, arrival_time, recovered=False, from_incomplete=False):
        """Output events from a packet"""
        if not packet.get('events'):
            return
        
        for key_down, duration_ms in packet['events']:
            if self.jitter_buffer:
                self.jitter_buffer.add_event(key_down, duration_ms, arrival_time)
            else:
                # Direct output without buffering
                self._on_cw_event(key_down, duration_ms)
        
        if self.debug:
            marker = " [RECOVERED]" if recovered else ""
            marker += " [INCOMPLETE]" if from_incomplete else ""
            print(f"Seq {packet['sequence']:3d}: {len(packet['events'])} events{marker}")
    
    def run(self):
        """Main receive loop"""
        print(f"\nListening on UDP port {self.port}...")
        
        try:
            while True:
                data, addr = self.socket.recvfrom(1024)
                arrival_time = time.time()
                
                self._process_packet(data, arrival_time)
        
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        if self.jitter_buffer:
            self.jitter_buffer.stop()
        self.gpio.cleanup()
        self.socket.close()
        
        # Print statistics
        print("\n" + "=" * 60)
        print("Reception Statistics:")
        print("=" * 60)
        print(f"Total packets received: {self.total_packets}")
        print(f"  Data packets: {self.data_packets}")
        print(f"  FEC packets: {self.fec_packets}")
        print(f"  Recovered packets: {self.recovered_packets}")
        print(f"  Duplicate packets: {self.duplicate_packets}")
        
        if self.jitter_buffer:
            stats = self.jitter_buffer.get_stats()
            if stats:
                print("\nJitter Buffer Statistics:")
                print(f"  Events processed: {stats['count']}")
                print(f"  Average delay: {stats['delay_avg']:.1f}ms")
                print(f"  Delay range: {stats['delay_min']:.1f}-{stats['delay_max']:.1f}ms")
                print(f"  Forward shifts: {stats['shifts']}")
                print(f"  Max queue depth: {stats['max_queue']}")
                print(f"  State errors: {stats['state_errors']}")
        
        print("=" * 60)
        print("GPIO cleaned up. 73!")


def _bcm_to_physical(bcm_pin):
    """Convert BCM pin number to physical pin number"""
    bcm_to_phys = {
        17: 11, 27: 13, 22: 15, 23: 16, 24: 18, 25: 22,
        5: 29, 6: 31, 12: 32, 13: 33, 19: 35, 16: 36, 26: 37, 20: 38, 21: 40
    }
    return bcm_to_phys.get(bcm_pin, "?")


def main():
    parser = argparse.ArgumentParser(description='CW GPIO Output with FEC for Raspberry Pi')
    parser.add_argument('--pin', type=int, default=17,
                        help='BCM GPIO pin number (default: 17 = physical pin 11)')
    parser.add_argument('--active-low', action='store_true',
                        help='Use active-low output (key-down = LOW)')
    parser.add_argument('--buffer', type=int, default=200,
                        help='Jitter buffer size in milliseconds (default: 200, recommended for FEC)')
    parser.add_argument('--port', type=int, default=UDP_PORT,
                        help=f'UDP port to listen on (default: {UDP_PORT})')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW GPIO Output with FEC for Raspberry Pi")
    print("=" * 60)
    print(f"GPIO Pin: BCM {args.pin} (physical pin {_bcm_to_physical(args.pin)})")
    print(f"Active: {'LOW' if args.active_low else 'HIGH'}")
    print(f"Buffer: {args.buffer}ms")
    print(f"UDP Port: {args.port}")
    print(f"FEC: Reed-Solomon (10 data + 6 redundancy packets)")
    print("=" * 60)
    print("\nHardware Setup:")
    print(f"  GPIO {args.pin} --> Relay/Transistor/Opto")
    print(f"  GND (Pin 6) --> Common ground")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)
    
    receiver = CWGPIOOutputFEC(
        port=args.port,
        gpio_pin=args.pin,
        active_high=not args.active_low,
        jitter_buffer_ms=args.buffer,
        debug=args.debug
    )
    
    receiver.run()


if __name__ == '__main__':
    main()
