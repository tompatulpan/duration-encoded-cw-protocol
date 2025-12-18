#!/usr/bin/env python3
"""
CW Protocol TCP with Timestamps
TCP implementation with relative timestamps for realtime sync
"""

import socket
import struct
import time
import threading
from cw_protocol import CWProtocol, UDP_PORT

# TCP Timestamp uses separate port from duration-based TCP
TCP_TS_PORT = 7356  # TCP timestamp protocol port
TCP_PORT = TCP_TS_PORT  # Alias for compatibility


class CWProtocolTCPTimestamp(CWProtocol):
    """TCP CW Protocol with relative timestamps for burst-resistant timing"""
    
    def __init__(self):
        super().__init__()
        self.sock = None
        self.listen_sock = None  # Separate listening socket
        self.recv_buffer = b''
        self.connected = False
        self.lock = threading.Lock()
        self.transmission_start = None  # Timestamp of first packet
        
    def connect(self, host, port=TCP_PORT, timeout=5.0):
        """Establish TCP connection to receiver"""
        try:
            if self.sock:
                self.close()
            
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Enable TCP keepalive to prevent idle connection drops
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Platform-specific keepalive tuning (Linux/Unix)
            if hasattr(socket, 'TCP_KEEPIDLE'):
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)    # Start after 60s idle
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)   # Probe every 10s
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)      # Drop after 3 failed probes
            
            self.sock.settimeout(timeout)
            self.sock.connect((host, port))
            self.sock.settimeout(None)
            self.connected = True
            self.transmission_start = None  # Reset on new connection
            return True
            
        except Exception as e:
            self.connected = False
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
            raise  # Re-raise exception for caller to handle
    
    def send_packet(self, key_down, duration_ms, sequence=None):
        """
        Send CW packet with timestamp
        
        Packet format (with length prefix):
            2 bytes: Length (network byte order)
            1 byte:  Sequence number
            1 byte:  Key state (0=UP, 1=DOWN)
            1-2 bytes: Duration (1 byte if <256ms, else 2 bytes big-endian)
            4 bytes: Relative timestamp in milliseconds (network byte order)
        
        Returns:
            True if sent successfully, False on error
        """
        if not self.connected or not self.sock:
            return False
        
        try:
            with self.lock:
                # Initialize transmission start time on first packet
                if self.transmission_start is None:
                    self.transmission_start = time.time()
                
                # Calculate relative timestamp (ms since transmission start)
                relative_time_ms = int((time.time() - self.transmission_start) * 1000)
                
                # Build packet
                if sequence is None:
                    sequence = self.sequence_number
                    self.sequence_number = (self.sequence_number + 1) % 256
                
                state_byte = 0x01 if key_down else 0x00
                
                # Encode duration
                if duration_ms < 256:
                    duration_bytes = struct.pack('B', duration_ms)
                else:
                    duration_bytes = struct.pack('!H', duration_ms)
                
                # Add timestamp (4 bytes, supports up to ~49 days)
                timestamp_bytes = struct.pack('!I', relative_time_ms)
                
                # Assemble packet
                packet = struct.pack('BB', sequence, state_byte) + duration_bytes + timestamp_bytes
                
                # Add length prefix
                length = struct.pack('!H', len(packet))
                framed_packet = length + packet
                
                # Send
                self.sock.sendall(framed_packet)
                return True
                
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            self.connected = False
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
            raise  # Re-raise for caller to handle reconnection
    
    def send_eot_packet(self):
        """Send End-of-Transmission packet"""
        if not self.connected or not self.sock:
            return False
        
        try:
            with self.lock:
                # EOT: special marker with timestamp
                packet = struct.pack('BB', self.sequence_number, 0xFF)
                packet += struct.pack('B', 0)  # Duration 0
                
                # Add timestamp
                if self.transmission_start is None:
                    relative_time_ms = 0
                else:
                    relative_time_ms = int((time.time() - self.transmission_start) * 1000)
                packet += struct.pack('!I', relative_time_ms)
                
                # Frame and send
                length = struct.pack('!H', len(packet))
                self.sock.sendall(length + packet)
                
                # Reset for next transmission
                self.transmission_start = None
                return True
                
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.connected = False
            return False
    
    def recv_packet(self):
        """
        Receive and parse timestamped packet
        
        Returns:
            (key_down, duration_ms, timestamp_ms) on success
            None on EOT or connection error
        """
        if not self.connected or not self.sock:
            return None
        
        try:
            # Read length prefix (2 bytes)
            while len(self.recv_buffer) < 2:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self.connected = False
                    return None
                self.recv_buffer += chunk
            
            # Parse length
            length = struct.unpack('!H', self.recv_buffer[:2])[0]
            self.recv_buffer = self.recv_buffer[2:]
            
            # Read packet data
            while len(self.recv_buffer) < length:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self.connected = False
                    return None
                self.recv_buffer += chunk
            
            # Extract packet
            packet = self.recv_buffer[:length]
            self.recv_buffer = self.recv_buffer[length:]
            
            # Parse packet
            if len(packet) < 7:  # Min: seq(1) + state(1) + dur(1) + ts(4)
                return None
            
            sequence = packet[0]
            state = packet[1]
            
            # Check for EOT
            if state == 0xFF:
                return None
            
            # Parse duration
            if len(packet) == 7:  # 1-byte duration
                duration_ms = packet[2]
                timestamp_ms = struct.unpack('!I', packet[3:7])[0]
            else:  # 2-byte duration
                duration_ms = struct.unpack('!H', packet[2:4])[0]
                timestamp_ms = struct.unpack('!I', packet[4:8])[0]
            
            key_down = (state == 0x01)
            
            return (key_down, duration_ms, timestamp_ms)
            
        except Exception as e:
            print(f"[TCP] Recv error: {e}")
            self.connected = False
            return None
    
    def listen(self, port=TCP_PORT, backlog=1):
        """Start TCP server (receiver side)"""
        try:
            if self.listen_sock:
                try:
                    self.listen_sock.close()
                except:
                    pass
            
            self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listen_sock.bind(('', port))
            self.listen_sock.listen(backlog)
            return True
            
        except Exception as e:
            print(f"[TCP] Listen failed: {e}")
            return False
    
    def accept(self):
        """Accept incoming connection (receiver side)"""
        try:
            # Close previous connection socket if exists
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
            
            # Accept new connection from listening socket
            conn, addr = self.listen_sock.accept()
            
            # Store connection socket
            self.sock = conn
            self.connected = True
            self.recv_buffer = b''
            self.transmission_start = None
            
            return addr
            
        except Exception as e:
            print(f"[TCP] Accept failed: {e}")
            return None
    
    def close(self):
        """Close TCP connection"""
        self.connected = False
        self.transmission_start = None
        
        # Close connection socket
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        
        # Close listening socket
        if self.listen_sock:
            try:
                self.listen_sock.close()
            except:
                pass
            self.listen_sock = None
