"""
Keyer module - wrapper for vail-adapter-lib keyer implementations

This module provides access to iambic keyer logic from the vail-adapter-lib package.
Instead of duplicating keyer code, we import from the shared library.

Usage:
    from keyer import IambicKeyer, IambicKeyerSync
    
    # For async applications (e.g., TCI):
    keyer = IambicKeyer(wpm=25, mode='B')
    
    # For sync applications (e.g., USB_HID senders):
    keyer = IambicKeyerSync(wpm=25, mode='B')
"""

import sys
import os

# Add vail-adapter-lib to path
_vail_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../vail-adapter-lib'))
if _vail_lib_path not in sys.path:
    sys.path.insert(0, _vail_lib_path)

# Import from vail-adapter-lib
from vail_adapter_lib import IambicKeyer, IambicKeyerSync

# Export main API
__all__ = ['IambicKeyer', 'IambicKeyerSync']
