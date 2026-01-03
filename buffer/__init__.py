"""
Buffer Module - Jitter buffering and event scheduling for CW protocol

This module provides buffering mechanisms to smooth out network jitter
and ensure proper timing of CW events.

Classes:
- JitterBuffer: Buffer CW events with adaptive word space detection
"""

from .jitter import JitterBuffer

__all__ = ['JitterBuffer']
