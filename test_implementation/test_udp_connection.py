#!/usr/bin/env python3
"""
Test UDP connection to remote receiver
Sends test packets and shows if they're getting through
"""

import socket
import time
import sys

def test_udp_connection(host, port=7355, packets=10):
    """Test UDP connection by sending packets"""
    
    print(f"Testing UDP connection to {host}:{port}")
    print(f"Sending {packets} test packets...")
    print("-" * 60)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    for i in range(packets):
        # Send test packet
        message = f"TEST PACKET {i+1}/{packets}".encode()
        sock.sendto(message, (host, port))
        print(f"Sent packet {i+1}")
        time.sleep(0.5)
    
    sock.close()
    
    print("-" * 60)
    print("✓ Packets sent successfully")
    print("\nCheck receiver for:")
    print("  - Firewall blocks (no packets received)")
    print("  - Router NAT issues (packets not forwarded)")
    print("  - Receiver not running (nobody listening)")
    print("\nIf receiver shows packets, UDP works!")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_udp_connection.py <host> [port]")
        print("\nExample:")
        print("  python3 test_udp_connection.py 203.0.113.42")
        print("  python3 test_udp_connection.py example.com 7355")
        return 1
    
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7355
    
    test_udp_connection(host, port)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
