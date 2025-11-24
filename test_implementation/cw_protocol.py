#!/usr/bin/env python3
"""
CW Protocol Implementation - DL4YHF-inspired
Simple UDP-based protocol for CW keying events
"""

import struct
import time

# Protocol constants
PROTOCOL_VERSION = 0x40  # 01 in bits 7-6
UDP_PORT = 7355

class CWProtocol:
    """DL4YHF-inspired CW protocol encoder/decoder"""
    
    def __init__(self):
        self.sequence_number = 0
        self.client_id = 0x42  # Default client ID
        
    def encode_timing(self, duration_ms):
        """
        Encode timing value using our optimized scheme
        
        Timing Encoding (optimized for CW):
          0x00-0x3F (0-63):   Direct milliseconds (good for 15-60 WPM)
          0x40-0x5F (64-95):  64 + 2*(value-64) ms (64-126ms)
          0x60-0x7F (96-127): 128 + 8*(value-96) ms (128-384ms)
        
        Returns: 7-bit timing value (0-127)
        """
        duration_ms = int(duration_ms)
        
        if duration_ms <= 63:
            # Direct encoding: 0-63ms with 1ms resolution
            return duration_ms
        elif duration_ms <= 126:
            # 2ms resolution: 64-126ms
            offset = (duration_ms - 64) // 2
            return 0x40 + offset  # 0x40-0x5F
        elif duration_ms <= 384:
            # 8ms resolution: 128-384ms
            offset = (duration_ms - 128) // 8
            return 0x60 + offset  # 0x60-0x7F
        else:
            # Cap at maximum
            return 0x7F
    
    def decode_timing(self, encoded):
        """
        Decode timing value
        
        Args:
            encoded: 7-bit encoded value (0-127)
            
        Returns: Duration in milliseconds
        """
        encoded = encoded & 0x7F  # Ensure 7 bits
        
        if encoded <= 0x3F:
            # Direct: 0-63ms
            return encoded
        elif encoded <= 0x5F:
            # 2ms resolution: 64-126ms
            return 64 + 2 * (encoded - 0x40)
        else:  # 0x60-0x7F
            # 8ms resolution: 128-384ms
            return 128 + 8 * (encoded - 0x60)
    
    def create_packet(self, key_down, duration_ms):
        """
        Create CW keying packet
        
        Packet format:
        Header (3 bytes):
          Byte 0: Protocol version and flags
            Bits 7-6: Protocol version (01)
            Bit  5:   Training mode (0)
            Bit  4:   Echo request (0)
            Bit  3:   Break request (0)
            Bit  2:   PTT state (0)
            Bits 1-0: Keyer mode (00=straight)
          Byte 1: Sequence number (0-255)
          Byte 2: Client ID
        
        Payload (1 byte per event):
          Bit 7: Key state (1=down, 0=up)
          Bits 6-0: Timing value
        
        Args:
            key_down: True if key pressed, False if released
            duration_ms: Duration since last state change
            
        Returns: bytes packet
        """
        # Header
        flags = PROTOCOL_VERSION  # Version 01, all flags 0
        seq = self.sequence_number & 0xFF
        client_id = self.client_id
        
        # Increment sequence number
        self.sequence_number = (self.sequence_number + 1) % 256
        
        # Payload - single event
        timing_encoded = self.encode_timing(duration_ms)
        event_byte = timing_encoded
        if key_down:
            event_byte |= 0x80  # Set bit 7 for key-down
        
        # Pack into bytes
        packet = struct.pack('BBB B', flags, seq, client_id, event_byte)
        
        return packet
    
    def parse_packet(self, packet_bytes):
        """
        Parse received CW packet
        
        Args:
            packet_bytes: Raw packet data
            
        Returns: dict with keys: version, sequence, client_id, events
                 events is list of (key_down, duration_ms) tuples
        """
        if len(packet_bytes) < 4:
            return None
        
        # Parse header
        flags, seq, client_id = struct.unpack('BBB', packet_bytes[0:3])
        
        # Extract version (bits 7-6)
        version = (flags >> 6) & 0x03
        
        # Parse events (rest of packet)
        events = []
        for i in range(3, len(packet_bytes)):
            event_byte = packet_bytes[i]
            key_down = bool(event_byte & 0x80)
            timing_encoded = event_byte & 0x7F
            duration_ms = self.decode_timing(timing_encoded)
            events.append((key_down, duration_ms))
        
        return {
            'version': version,
            'sequence': seq,
            'client_id': client_id,
            'events': events
        }


class CWTimingStats:
    """Track timing statistics for analysis"""
    
    def __init__(self):
        self.events = []
        self.start_time = time.time()
        
    def add_event(self, key_down, duration_ms, timestamp=None):
        """Record a CW event"""
        if timestamp is None:
            timestamp = time.time() - self.start_time
        
        self.events.append({
            'timestamp': timestamp,
            'key_down': key_down,
            'duration_ms': duration_ms
        })
    
    def get_stats(self):
        """Calculate statistics"""
        if not self.events:
            return {}
        
        dits = []
        dahs = []
        spaces = []
        
        for event in self.events:
            duration = event['duration_ms']
            if event['key_down']:
                # Classify as dit or dah (threshold at 2x dit length)
                if len(dits) > 0:
                    avg_dit = sum(dits) / len(dits)
                    if duration > avg_dit * 1.5:
                        dahs.append(duration)
                    else:
                        dits.append(duration)
                else:
                    # First element, assume dit if < 100ms, else dah
                    if duration < 100:
                        dits.append(duration)
                    else:
                        dahs.append(duration)
            else:
                spaces.append(duration)
        
        stats = {
            'total_events': len(self.events),
            'duration_sec': self.events[-1]['timestamp'] if self.events else 0
        }
        
        if dits:
            avg_dit = sum(dits) / len(dits)
            stats['avg_dit_ms'] = avg_dit
            stats['wpm'] = 1200 / avg_dit if avg_dit > 0 else 0
            stats['dit_count'] = len(dits)
        
        if dahs:
            stats['avg_dah_ms'] = sum(dahs) / len(dahs)
            stats['dah_count'] = len(dahs)
            if dits:
                stats['dah_dit_ratio'] = stats['avg_dah_ms'] / stats['avg_dit_ms']
        
        if spaces:
            stats['avg_space_ms'] = sum(spaces) / len(spaces)
            stats['space_count'] = len(spaces)
        
        return stats


if __name__ == '__main__':
    # Test encoding/decoding
    protocol = CWProtocol()
    
    print("Testing timing encoding/decoding:")
    test_values = [1, 10, 30, 60, 80, 100, 150, 200, 300, 380]
    
    for val in test_values:
        encoded = protocol.encode_timing(val)
        decoded = protocol.decode_timing(encoded)
        error = abs(decoded - val)
        print(f"{val:3d}ms -> 0x{encoded:02X} -> {decoded:3d}ms (error: {error:2d}ms)")
    
    print("\nTesting packet creation:")
    # Simulate "E" at 20 WPM (60ms dit)
    packet = protocol.create_packet(key_down=True, duration_ms=60)
    print(f"Key down packet: {packet.hex()}")
    
    parsed = protocol.parse_packet(packet)
    print(f"Parsed: {parsed}")
    
    # Multiple events in one packet (batch)
    print("\nTesting batch packet (letter 'A' = dit-dah):")
    # Manually create multi-event packet
    flags = PROTOCOL_VERSION
    seq = 5
    client_id = 0x42
    
    # Event 1: Key down 60ms (dit)
    event1 = 0x80 | protocol.encode_timing(60)
    # Event 2: Key up 60ms (inter-element space)
    event2 = protocol.encode_timing(60)
    # Event 3: Key down 180ms (dah)
    event3 = 0x80 | protocol.encode_timing(180)
    # Event 4: Key up 60ms (end)
    event4 = protocol.encode_timing(60)
    
    batch_packet = struct.pack('BBB BBBB', flags, seq, client_id,
                                event1, event2, event3, event4)
    print(f"Batch packet: {batch_packet.hex()}")
    
    parsed = protocol.parse_packet(batch_packet)
    print(f"Parsed: {parsed}")
    print("Events:")
    for i, (kd, dur) in enumerate(parsed['events']):
        state = "DOWN" if kd else "UP  "
        print(f"  {i+1}. {state} {dur:3d}ms")
