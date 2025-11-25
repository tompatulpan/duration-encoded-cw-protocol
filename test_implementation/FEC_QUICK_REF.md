# FEC Quick Reference

## Testing FEC Performance

```bash
# Simulate 20% packet loss
python3 test_fec.py 20

# Simulate 40% packet loss
python3 test_fec.py 40

# Test specific method
python3 test_fec.py 30 interpolate
python3 test_fec.py 30 duplicate
```

## Using FEC in Production

### Receiver with Interpolation (Recommended)

```bash
# Standard receiver with FEC
python3 cw_receiver_fec.py --jitter-buffer 100 --interpolate

# Without interpolation (standard mode)
python3 cw_receiver_fec.py --jitter-buffer 100 --no-interpolate
```

### Sender with Duplication (for severe loss)

```python
from cw_fec import CWProtocolFEC
import socket

# Create protocol with 2x duplication
proto = CWProtocolFEC(fec_mode='duplicate', fec_param=2)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Send event - automatically duplicated
packets = proto.create_packet_with_fec(key_down=True, duration_ms=60)
for pkt in packets:
    sock.sendto(pkt, ('receiver.example.com', 7355))
```

## When to Use What

| Network Condition | Packet Loss | Recommended FEC | Bandwidth | Recovery |
|-------------------|-------------|-----------------|-----------|----------|
| Excellent LAN     | < 1%        | None            | 1x        | 99%      |
| Good Internet     | 1-10%       | Interpolation   | 1x        | 99%+     |
| WiFi/Mobile       | 10-20%      | Interpolation   | 1x        | 95%+     |
| Unreliable Link   | 20-30%      | 2x Duplication  | 2x        | 94%      |
| Poor Connection   | 30-40%      | 3x Duplication  | 3x        | 100%     |
| Extreme Loss      | > 40%       | Fix network!    | -         | -        |

## Quick Comparison

### Interpolation
✅ Zero bandwidth overhead  
✅ Perfect for < 30% loss  
✅ Automatic (no sender changes)  
❌ Cannot recover large gaps  
❌ Requires predictable CW patterns  

**Use when:** Internet/WiFi with occasional packet drops

### 2x Duplication  
✅ Works for any content  
✅ 94% recovery at 20% loss  
❌ 2x bandwidth usage  
❌ Requires sender modification  

**Use when:** Moderate loss (10-30%), bandwidth available

### 3x Duplication
✅ Near-perfect recovery (40% loss)  
✅ Works for any content  
❌ 3x bandwidth usage  
❌ Requires sender modification  

**Use when:** Severe loss (30-50%), mission critical

## Files

- `cw_fec.py` - FEC protocol implementation
- `test_fec.py` - Performance testing tool
- `cw_receiver_fec.py` - Receiver with auto-interpolation
- `FEC_GUIDE.md` - Complete documentation

## Examples

### Measure Your Network Loss

```bash
# Terminal 1: Start receiver with statistics
python3 cw_receiver.py --jitter-buffer 100

# Terminal 2: Send test message
python3 cw_auto_sender.py <host> 25 "HELLO WORLD"

# Check "Packets lost" in receiver output
# This tells you which FEC mode to use
```

### Test Interpolation Effectiveness

```bash
# Test with simulated loss
python3 test_fec.py 25 interpolate

# Check recovery rate:
# > 95%: Interpolation working great
# < 90%: Consider duplication FEC
```

### Enable FEC on Existing Setup

```bash
# Just replace cw_receiver.py with cw_receiver_fec.py
python3 cw_receiver_fec.py --jitter-buffer 100 --interpolate

# No sender changes needed!
```
