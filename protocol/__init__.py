"""
CW Protocol Module - Duration-Encoded CW Protocol Implementation

This module provides the core protocol implementation for transmitting
Morse code timing over networks (UDP and TCP).

Main classes:
- CWProtocolBase: Abstract base class for protocol variants
- CWTimingStats: Track and analyze CW timing statistics
- UDP_PORT: Default UDP port (7355)
- PROTOCOL_VERSION: Current protocol version

For concrete implementations, see:
- protocol.udp for UDP transport
- protocol.udp_ts for UDP transport (timestamp-based)
- protocol.tcp_ts for TCP transport (timestamp-based)
"""

from .base import CWProtocolBase, PROTOCOL_VERSION, UDP_PORT
from .stats import CWTimingStats

__all__ = [
    'CWProtocolBase',
    'CWTimingStats',
    'PROTOCOL_VERSION',
    'UDP_PORT'
]
