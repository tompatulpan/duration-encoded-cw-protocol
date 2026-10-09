#!/usr/bin/env python3
"""
Base CW Protocol - Abstract base class for all protocol variants
"""

import struct

# Protocol constants
PROTOCOL_VERSION = 0x40  # 01 in bits 7-6
UDP_PORT = 7355


class CWProtocolBase:
    """Duration-Encoded CW (DECW) Protocol base class
    
    Custom protocol for transmitting Morse code timing over UDP/TCP.
    Encodes key state changes with precise timing information using
    optimized variable-resolution encoding.
    
    This is an abstract base class - use concrete implementations:
    - CWProtocolUDP for UDP transport (duration-based)
    - CWProtocolUDPTimestamp for UDP transport (timestamp-based)
    - CWProtocolTCPTimestamp for TCP transport (timestamp-based)
    """
    
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
            offset = min((duration_ms - 128) // 8, 31)  # Clamp to 7 bits
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
    
    def create_packet(self, key_down, duration_ms, sequence=None):
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
            sequence: Optional sequence number override
            
        Returns: bytes packet
        """
        # Header
        flags = PROTOCOL_VERSION  # Version 01, all flags 0
        if sequence is not None:
            seq = sequence & 0xFF
        else:
            seq = self.sequence_number & 0xFF
            # Increment sequence number
            self.sequence_number = (self.sequence_number + 1) % 256
        client_id = self.client_id
        
        # Payload - single event
        timing_encoded = self.encode_timing(duration_ms)
        event_byte = timing_encoded
        if key_down:
            event_byte |= 0x80  # Set bit 7 for key-down
        
        # Pack into bytes
        packet = struct.pack('BBBB', flags, seq, client_id, event_byte)
        
        return packet
    
    def create_eot_packet(self):
        """
        Create End-of-Transmission packet
        
        Special packet with Break Request flag set and no payload.
        Signals that transmission is complete and receiver should drain buffer.
        
        Returns: bytes packet
        """
        # Set Break Request flag (bit 3)
        flags = PROTOCOL_VERSION | 0x08  # Version 01, Break=1
        seq = self.sequence_number & 0xFF
        self.sequence_number = (self.sequence_number + 1) % 256
        client_id = self.client_id
        
        # Pack header only (no payload for EOT)
        packet = struct.pack('BBB', flags, seq, client_id)
        
        return packet
    
    def parse_packet(self, packet_bytes):
        """
        Parse received CW packet
        
        Args:
            packet_bytes: Raw packet data
            
        Returns: dict with keys: version, sequence, client_id, events
                 events is list of (key_down, duration_ms) tuples
        """
        # Accept 3-byte EOT packets (header only) and 4+ byte data packets
        if len(packet_bytes) < 3:
            return None
        
        # Parse header
        flags, seq, client_id = struct.unpack('BBB', packet_bytes[0:3])
        
        # Extract version (bits 7-6)
        version = (flags >> 6) & 0x03
        
        # Check for End-of-Transmission (Break Request flag, bit 3)
        is_eot = bool(flags & 0x08)
        
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
            'events': events,
            'eot': is_eot
        }
