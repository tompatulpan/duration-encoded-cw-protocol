"""
Audio Module - Audio output and GPIO control for CW keying

This module provides audio sidetone generation and GPIO output
for CW keying applications.

Classes:
- SidetoneGenerator: Generate audio sidetone for CW feedback
- GPIOKeyer: Control hardware via Raspberry Pi GPIO (optional)
"""

from .sidetone import SidetoneGenerator
from .gpio import GPIOKeyer

__all__ = ['SidetoneGenerator', 'GPIOKeyer']
