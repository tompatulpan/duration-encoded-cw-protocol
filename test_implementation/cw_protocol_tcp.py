#!/usr/bin/env python3
"""
CW Protocol TCP Implementation
TCP wrapper around CWProtocol with stream framing and connection management
"""

import socket
import struct
import time
import threading
from cw_protocol import CWProtocol, UDP_PORT

# TCP uses same default port as UDP
TCP_PORT = UDP_PORT


class CWProtocolTCP(CWProtocol):
    """TCP wrapper for CW Protocol with length-prefix framing"""
    
    def __init__(self):
        super().__init__()
        self.sock = None
        self.recv_buffer = b''
        self.connected = False
        self.lock = threading.Lock()  # Thread-safe socket operations
        
    def connect(self, host, port=TCP_PORT, timeout=5.0):
        """
        Establish TCP connection to receiver
        
        Args:
            host: Receiver hostname/IP
            port: TCP port (default: 7355)
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected, False on failure
        """
        try:
            if self.sock:
                self.close()
            
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((host, port))
            self.sock.settimeout(None)  # Blocking mode after connection
            self.connected = True
            return True
            
        except Exception as e:
            print(f"[TCP] Connection failed: {e}")
            self.connected = False
            return False
    
    def send_packet(self, key_down, duration_ms, sequence=None):
        """
        Send CW packet over TCP with length prefix
        
        Packet format:
            2 bytes: Length (network byte order, big-endian)
            N bytes: CW packet data
        
        Args:
            key_down: Key state (True=down, False=up)
            duration_ms: Duration in milliseconds
            sequence: Optional sequence number override
            
        Returns:
            True if sent successfully, False on error
        """
        if not self.connected or not self.sock:
            return False
        
        try:
            with self.lock:
                # Create CW packet (uses parent class method)
                packet = self.create_packet(key_down, duration_ms, sequence)
                
                # Add length prefix (2 bytes, network byte order)
                length = struct.pack('!H', len(packet))
                framed_packet = length + packet
                
                # Send all bytes
                self.sock.sendall(framed_packet)
                return True
                
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[TCP] Send failed: {e}")
            self.connected = False
            return False
    
    def send_eot_packet(self):
        """
        Send End-of-Transmission packet
        
        Returns:
            True if sent successfully, False on error
        """
        if not self.connected or not self.sock:
            return False
        
        try:
            with self.lock:
                # Create EOT packet (uses parent class method)
                packet = self.create_eot_packet()
                
                # Add length prefix
                length = struct.pack('!H', len(packet))
                framed_packet = length + packet
                
                # Send all bytes
                self.sock.sendall(framed_packet)
                return True
                
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[TCP] Send EOT failed: {e}")
            self.connected = False
            return False
    
    def recv_packet(self, timeout=None):
        """
        Receive one framed CW packet from TCP stream
        
        Args:
            timeout: Receive timeout in seconds (None = blocking)
            
        Returns:
            Parsed packet dict, or None on error/timeout
        """
        if not self.connected or not self.sock:
            return None
        
        try:
            # Set socket timeout if specified
            if timeout is not None:
                self.sock.settimeout(timeout)
            
            with self.lock:
                # Read 2-byte length prefix
                while len(self.recv_buffer) < 2:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        # Connection closed
                        self.connected = False
                        return None
                    self.recv_buffer += chunk
                
                # Extract length
                length = struct.unpack('!H', self.recv_buffer[0:2])[0]
                
                # Read packet data (wait for complete packet)
                total_needed = 2 + length
                while len(self.recv_buffer) < total_needed:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        # Connection closed mid-packet
                        self.connected = False
                        return None
                    self.recv_buffer += chunk
                
                # Extract packet
                packet_data = self.recv_buffer[2:2+length]
                self.recv_buffer = self.recv_buffer[2+length:]  # Remove from buffer
                
                # Parse packet (uses parent class method)
                parsed = self.parse_packet(packet_data)
                return parsed
                
        except socket.timeout:
            return None
        except (ConnectionResetError, OSError) as e:
            print(f"[TCP] Receive failed: {e}")
            self.connected = False
            return None
        finally:
            # Restore blocking mode
            if timeout is not None:
                try:
                    self.sock.settimeout(None)
                except:
                    pass
    
    def is_connected(self):
        """Check if connection is active"""
        return self.connected and self.sock is not None
    
    def close(self):
        """Close TCP connection"""
        self.connected = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        self.recv_buffer = b''


class CWServerTCP:
    """TCP server for receiving CW packets"""
    
    def __init__(self, port=TCP_PORT, bind_address='0.0.0.0'):
        """
        Initialize TCP server
        
        Args:
            port: TCP port to listen on
            bind_address: Interface to bind (0.0.0.0 = all interfaces)
        """
        self.port = port
        self.bind_address = bind_address
        self.server_sock = None
        self.client_sock = None
        self.client_addr = None
        self.protocol = CWProtocolTCP()
        self.running = False
        
    def start(self):
        """
        Start TCP server and listen for connections
        
        Returns:
            True if server started, False on error
        """
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind((self.bind_address, self.port))
            self.server_sock.listen(1)  # Only accept 1 connection at a time
            self.running = True
            return True
            
        except Exception as e:
            print(f"[TCP Server] Failed to start: {e}")
            return False
    
    def accept_connection(self, timeout=None):
        """
        Wait for incoming connection
        
        Args:
            timeout: Accept timeout in seconds (None = blocking)
            
        Returns:
            True if connection accepted, False on timeout/error
        """
        if not self.running or not self.server_sock:
            return False
        
        try:
            if timeout is not None:
                self.server_sock.settimeout(timeout)
            
            self.client_sock, self.client_addr = self.server_sock.accept()
            self.protocol.sock = self.client_sock
            self.protocol.connected = True
            
            # Restore blocking mode
            if timeout is not None:
                self.server_sock.settimeout(None)
            
            return True
            
        except socket.timeout:
            return False
        except Exception as e:
            print(f"[TCP Server] Accept failed: {e}")
            return False
    
    def recv_packet(self, timeout=None):
        """
        Receive packet from connected client
        
        Args:
            timeout: Receive timeout in seconds
            
        Returns:
            Parsed packet dict, or None on error
        """
        if not self.protocol.is_connected():
            return None
        
        return self.protocol.recv_packet(timeout)
    
    def close_client(self):
        """Close current client connection"""
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
            self.client_sock = None
            self.client_addr = None
            self.protocol.sock = None
            self.protocol.connected = False
    
    def stop(self):
        """Stop server and close all connections"""
        self.running = False
        self.close_client()
        if self.server_sock:
            try:
                self.server_sock.close()
            except:
                pass
            self.server_sock = None


if __name__ == '__main__':
    # Test TCP framing
    print("Testing TCP Protocol Framing")
    print("=" * 60)
    
    # Client protocol
    client = CWProtocolTCP()
    
    # Test packet creation
    print("\n1. Testing packet creation:")
    packet = client.create_packet(key_down=True, duration_ms=60)
    print(f"   CW packet (60ms key-down): {packet.hex()} ({len(packet)} bytes)")
    
    # Test framing
    print("\n2. Testing length-prefix framing:")
    length_prefix = struct.pack('!H', len(packet))
    framed = length_prefix + packet
    print(f"   Framed packet: {framed.hex()} ({len(framed)} bytes)")
    print(f"   Length prefix: {length_prefix.hex()} = {len(packet)} bytes")
    
    # Test parsing
    print("\n3. Testing packet parsing:")
    parsed = client.parse_packet(packet)
    print(f"   Parsed: {parsed}")
    
    # Test server creation
    print("\n4. Testing server initialization:")
    server = CWServerTCP(port=7355)
    print(f"   Server created for port {server.port}")
    
    print("\n✓ TCP protocol wrapper tests passed")
    print("\nUsage:")
    print("  Sender: python3 cw_sender_tcp.py <host>")
    print("  Receiver: python3 cw_receiver_tcp.py")
