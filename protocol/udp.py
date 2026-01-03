#!/usr/bin/env python3
"""
UDP Protocol Implementation - Duration-Encoded CW over UDP
"""

import socket
from .base import CWProtocolBase, UDP_PORT


class CWProtocolUDP(CWProtocolBase):
    """Duration-Encoded CW Protocol for UDP transport
    
    Simple UDP datagram transport - best for LAN use.
    Packets may be lost or arrive out of order.
    """
    
    def __init__(self, host=None, port=UDP_PORT):
        """
        Initialize UDP protocol
        
        Args:
            host: Target host (for client mode), None for server mode
            port: UDP port number (default: 7355)
        """
        super().__init__()
        self.host = host
        self.port = port
        self.sock = None
        
    def connect(self):
        """Create UDP socket for sending"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Set buffer size for better burst handling
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024*1024)
        except:
            pass  # Ignore if not supported
    
    def bind(self, host='0.0.0.0'):
        """Bind UDP socket for receiving"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Set buffer size for better burst handling
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)
        except:
            pass  # Ignore if not supported
        self.sock.bind((host, self.port))
    
    def send_packet(self, key_down, duration_ms):
        """Send CW event packet via UDP"""
        packet = self.create_packet(key_down, duration_ms)
        self.sock.sendto(packet, (self.host, self.port))
    
    def send_eot(self):
        """Send End-of-Transmission packet"""
        packet = self.create_eot_packet()
        self.sock.sendto(packet, (self.host, self.port))
    
    def recv_packet(self, timeout=None):
        """
        Receive and parse CW packet from UDP
        
        Args:
            timeout: Socket timeout in seconds (None = blocking)
            
        Returns: Parsed packet dict or None on timeout/error
        """
        if timeout is not None:
            self.sock.settimeout(timeout)
        
        try:
            data, addr = self.sock.recvfrom(1024)
            return self.parse_packet(data)
        except socket.timeout:
            return None
        except Exception as e:
            print(f"[ERROR] UDP receive error: {e}")
            return None
    
    def close(self):
        """Close UDP socket"""
        if self.sock:
            self.sock.close()
            self.sock = None
