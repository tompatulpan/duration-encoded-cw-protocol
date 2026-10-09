# CW Jitter Buffer - Quick Reference

## Problem

When transmitting CW over the internet, you hear:
- ❌ Uneven timing (stuttering)
- ❌ Irregular dits and dahs
- ❌ "Jittery" sound quality

**Cause:** Variable network delays (jitter)

## Solution

Enable the **jitter buffer** on the receiver.

## Commands

### For LAN/Local Testing
```bash
python3 cw_receiver.py
```
✓ No buffer needed  
✓ Minimal latency

### For Internet Use
```bash
python3 cw_receiver.py --jitter-buffer 100
```
✓ Smooth timing  
✓ Professional quality  
⚠️ Adds 100ms latency

## Buffer Size Guide

| Network | Command | Latency |
|---------|---------|---------|
| LAN | `--jitter-buffer 0` (or omit) | 0ms |
| Good Internet | `--jitter-buffer 50` | 50ms |
| **Standard** ⭐ | `--jitter-buffer 100` | 100ms |
| Poor Internet | `--jitter-buffer 150` | 150ms |
| Satellite | `--jitter-buffer 200` | 200ms |

## Test It Yourself

**Without buffer (you'll hear jitter):**
```bash
# Terminal 1
python3 cw_receiver.py

# Terminal 2
python3 test_jitter_buffer.py --jitter 50
```

**With buffer (smooth):**
```bash
# Terminal 1
python3 cw_receiver.py --jitter-buffer 100

# Terminal 2
python3 test_jitter_buffer.py --jitter 50
```

## All Options

```bash
python3 cw_receiver.py --help
```

Available options:
- `--port 7355` - UDP port (default: 7355)
- `--jitter-buffer 100` - Buffer in ms (0=disabled)
- `--no-audio` - Visual only, no sidetone

## Port Forwarding Setup

For internet access, configure your router:

1. **Login** to router admin
2. **Port Forwarding** section
3. **Add rule:**
   - Protocol: **UDP**
   - External Port: **7355**
   - Internal IP: **Your computer's LAN IP**
   - Internal Port: **7355**
4. **Save** and test

## Visual Indicators

```
[████████████] DOWN  60ms | Seq: 42 Pkts: 156 Lost: 0 JBuf: 3
                                                        ^^^^^^
```

**JBuf meaning:**
- `JBuf: 0` - Empty (caught up)
- `JBuf: 1-5` - ✓ Normal
- `JBuf: >10` - ⚠️ Congestion or buffer too small

## Troubleshooting

### Still hearing jitter?
➜ Increase buffer:
```bash
python3 cw_receiver.py --jitter-buffer 150
```

### Too much delay?
➜ Decrease buffer:
```bash
python3 cw_receiver.py --jitter-buffer 50
```

### High packet loss?
➜ Check network:
```bash
ping -c 100 <remote_ip>
```

Look for:
- High latency (>100ms)
- Packet loss (>1%)
- Variable times (jitter)

## Complete Documentation

- **Quick Start:** This file
- **Complete Guide:** `JITTER_BUFFER.md`
- **Test Implementation:** `test_jitter_buffer.py`
- **Specification:** `../CW_PROTOCOL_SPECIFICATION.md` (Section 6.3.3)

---

**TL;DR:** Use `--jitter-buffer 100` for internet, omit for LAN.
