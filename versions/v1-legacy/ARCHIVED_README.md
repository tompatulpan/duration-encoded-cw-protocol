# test_implementation/ - ARCHIVED

**Status:** This directory contains legacy implementations using old import patterns and duplicate code.

**Replacement:** Use the clean implementations in `../apps/` instead.

## Migration Mapping

### Use these NEW files instead (apps/):

| Old (test_implementation/) | New (apps/) | Status |
|---------------------------|-------------|--------|
| cw_auto_sender_tcp_ts.py | test_sender_tcp_ts.py | ✅ Replaced |
| cw_auto_sender_udp_ts.py | test_sender_udp_ts.py | ✅ Replaced |
| cw_receiver_tcp_ts.py | test_receiver_tcp_ts.py | ✅ Replaced |
| cw_receiver_udp_ts.py | test_receiver_udp_ts.py | ✅ Replaced |
| cw_receiver.py (UDP) | test_receiver_udp.py | ✅ Replaced |
| cw_usb_key_sender_tcp_ts.py | (use USB_HID/ senders) | ⚠️ Use USB_HID project |
| cw_usb_key_sender_udp_ts.py | (use USB_HID/ senders) | ⚠️ Use USB_HID project |

### Protocol Files (now in protocol/ module):

| Old File | New Location |
|----------|--------------|
| cw_protocol.py | protocol/udp.py |
| cw_protocol_tcp_ts.py | protocol/tcp_ts.py |
| cw_protocol_udp_ts.py | protocol/udp_ts.py |
| cw_protocol_tcp.py | (deprecated, no duration-only in new structure) |

### Shared Components (now in modules):

| Old Location | New Location |
|--------------|--------------|
| cw_receiver.py (JitterBuffer class) | buffer/jitter.py |
| cw_receiver.py (SidetoneGenerator class) | audio/sidetone.py |
| cw_receiver.py (GPIOKeyer class) | audio/gpio.py |
| IambicKeyer classes (duplicated 8× in senders) | keyer/ (wraps vail-adapter-lib) |

## Why Archived?

1. **Code duplication:** Contains ~1,500 lines of duplicate classes (IambicKeyer, JitterBuffer, SidetoneGenerator)
2. **Old import patterns:** Uses `from cw_protocol import ...` instead of modular imports
3. **Superseded:** apps/ provides cleaner, working examples with modular structure
4. **Maintenance burden:** Updating old code is less valuable than using new structure

## If You Need Something From Here:

1. **First check apps/**: The new implementations are simpler and cleaner
2. **For specific features**: Extract only what's needed and port to modular imports
3. **For reference**: This code remains available but is not actively maintained

## Historical Context:

- Created: Late 2024 (initial protocol development)
- Archived: January 2026 (after modular restructuring completed)
- Commit: See git history for original implementations
