#!/usr/bin/env python3
"""
CW Protocol UDP with Timestamps
UDP implementation with relative timestamps for realtime sync and burst resistance
"""

import socket
import struct
import time
from cw_protocol import CWProtocol, UDP_PORT

# UDP Timestamp uses separate port
UDP_TS_PORT = 7357  # UDP timestamp protocol port


class CWProtocolUDPTimestamp(CWProtocol):
    """UDP CW Protocol with relative timestamps for burst-resistant timing"""
    
    def __init__(self):
        super().__init__()
        self.sock = None
        self.transmission_start = None  # Timestamp of first packet
        self.last_sequence = None  # Track sequence numbers
        self.packets_received = 0  # Statistics
        self.packets_lost = 0  # Statistics
        
    def create_socket(self, port=UDP_TS_PORT):
        """Create UDP socket"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', port))
        return self.sock
    
    def send_packet(self, key_down, duration_ms, dest_addr):
        """
        Send timestamped UDP packet
        
        Args:
            key_down: bool - key state
            duration_ms: int - duration in milliseconds
            dest_addr: tuple - (host, port) destination
        """
        # Initialize transmission start time on first packet
        if self.transmission_start is None:
            self.transmission_start = time.time()
            timestamp_ms = 0
        else:
            # Calculate relative timestamp (milliseconds since start)
            timestamp_ms = int((time.time() - self.transmission_start) * 1000)
        
        # Encode packet
        state_byte = 1 if key_down else 0
        
        # Encode duration (1 or 2 bytes)
        if duration_ms <= 255:
            duration_bytes = struct.pack('B', duration_ms)
        else:
            duration_bytes = struct.pack('!H', duration_ms)  # Big-endian 16-bit
        
        # Encode timestamp (4 bytes, big-endian)
        timestamp_bytes = struct.pack('!I', timestamp_ms)
        
        # Build packet: [sequence] [state] [duration] [timestamp]
        packet = struct.pack('B', self.sequence_number)
        packet += struct.pack('B', state_byte)
        packet += duration_bytes
        packet += timestamp_bytes
        
        # Send packet
        self.sock.sendto(packet, dest_addr)
        
        # Increment sequence number
        self.sequence_number = (self.sequence_number + 1) % 256
    
    def recv_packet(self):
        """
        Receive timestamped UDP packet
        
        Returns:
            tuple: (key_down, duration_ms, timestamp_ms, sender_addr) or None on timeout
            Special: Returns ('EOT', 0, timestamp_ms, sender_addr) for end-of-transmission
        """
        try:
            data, addr = self.sock.recvfrom(1024)
            
            if len(data) < 7:  # Minimum: seq(1) + state(1) + duration(1) + timestamp(4)
                return None
            
            # Check for EOT packet first
            if self.is_eot_packet(data):
                timestamp_ms = struct.unpack('!I', data[3:7])[0]
                return ('EOT', 0, timestamp_ms, addr)
            
            # Parse packet
            sequence = data[0]
            state_byte = data[1]
            key_down = (state_byte == 1)
            
            # Parse duration (check packet length)
            if len(data) == 7:
                # 1-byte duration
                duration_ms = data[2]
                timestamp_ms = struct.unpack('!I', data[3:7])[0]
            elif len(data) == 8:
                # 2-byte duration
                duration_ms = struct.unpack('!H', data[2:4])[0]
                timestamp_ms = struct.unpack('!I', data[4:8])[0]
            else:
                return None
            
            # Track sequence
            if self.last_sequence is not None:
                expected = (self.last_sequence + 1) % 256
                if sequence != expected:
                    self.packets_lost += abs(sequence - expected)
            
            self.last_sequence = sequence
            self.packets_received += 1
            
            return (key_down, duration_ms, timestamp_ms, addr)
            
        except socket.timeout:
            return None
        except Exception as e:
            print(f"[ERROR] recv_packet failed: {e}")
            return None
    
    def send_eot_packet(self, dest_addr):
        """
        Send End-of-Transmission marker
        
        Args:
            dest_addr: tuple - (host, port) destination
        """
        # EOT packet: [sequence] [0xFF] [0x00] [timestamp]
        timestamp_ms = 0
        if self.transmission_start is not None:
            timestamp_ms = int((time.time() - self.transmission_start) * 1000)
        
        timestamp_bytes = struct.pack('!I', timestamp_ms)
        
        eot_packet = struct.pack('BBB', self.sequence_number, 0xFF, 0x00)
        eot_packet += timestamp_bytes
        
        self.sock.sendto(eot_packet, dest_addr)
        self.sequence_number = (self.sequence_number + 1) % 256
        
        # Reset transmission start for next transmission
        self.transmission_start = None
    
    def is_eot_packet(self, data):
        """Check if packet is End-of-Transmission marker"""
        if len(data) >= 3:
            return data[1] == 0xFF and data[2] == 0x00
        return False
    
    def close(self):
        """Close socket"""
        if self.sock:
            self.sock.close()
            self.sock = None


if __name__ == '__main__':
    print("CW Protocol UDP with Timestamps")
    print("================================")
    print(f"Default port: {UDP_TS_PORT}")
    print("\nPacket format:")
    print("  [sequence(1)] [state(1)] [duration(1-2)] [timestamp(4)]")
    print("  Total: 7-8 bytes per packet")
    print("\nTimestamp: Relative milliseconds since transmission start")
    print("  - First packet: timestamp = 0")
    print("  - Subsequent: timestamp = ms since first packet")
    print("  - 32-bit unsigned, big-endian")
