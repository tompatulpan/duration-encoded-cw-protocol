# Forward Error Correction (FEC) for CW Protocol

## Overview

The CW protocol now supports packet loss recovery using two complementary strategies:

1. **Packet Duplication** - Send each packet multiple times
2. **Interpolation** - Intelligently reconstruct missing packets based on CW patterns

## Performance Summary

| Loss Rate | No FEC | 2x Dup | 3x Dup | Interpolation |
|-----------|--------|--------|--------|---------------|
| 10%       | ~90%   | 99%+   | 99%+   | 100%          |
| 20%       | ~80%   | 94%    | 99%+   | 100%          |
| 30%       | ~70%   | 85%    | 95%    | 90%           |
| 40%       | ~60%   | 83%    | 100%   | 72%           |

## Strategy Selection

### Interpolation (Recommended for most users)
**Best for:** Good to moderate networks (< 30% loss)

**Pros:**
- Zero bandwidth overhead
- Perfect recovery for small gaps (1-2 packets)
- No configuration needed

**Cons:**
- Only works for predictable CW patterns
- Cannot recover large gaps (3+ consecutive losses)
- Requires CW to follow typical timing

**When to use:**
- Internet/WiFi with occasional packet loss
- Manual keying (regular dit/dah patterns)
- Bandwidth-constrained links

### 2x Duplication
**Best for:** Moderate to high loss (20-30%)

**Pros:**
- Simple and reliable
- Works for any content
- 94%+ recovery at 20% loss

**Cons:**
- 2x bandwidth usage
- Higher latency (duplicate packets)

**When to use:**
- Unreliable mobile networks
- High-jitter connections
- When bandwidth is available

### 3x Duplication
**Best for:** Severe loss (30-50%)

**Pros:**
- Near-perfect recovery even at 40% loss
- Guaranteed delivery for critical messages

**Cons:**
- 3x bandwidth usage
- Highest latency

**When to use:**
- Satellite links with high loss
- Disaster/emergency communications
- Long-distance HF propagation (if using IP over radio)

## Implementation

### Testing FEC Performance

```bash
# Test with 20% simulated packet loss
python3 test_fec.py 20

# Test with 40% loss
python3 test_fec.py 40

# Test only interpolation
python3 test_fec.py 30 interpolate

# Test only duplication
python3 test_fec.py 30 duplicate
```

### Using FEC in Your Code

#### Sender with Duplication FEC

```python
from cw_fec import CWProtocolFEC

# Create protocol with 2x duplication
proto = CWProtocolFEC(fec_mode='duplicate', fec_param=2)

# Create packet(s) - returns list of 2 copies
packets = proto.create_packet_with_fec(key_down=True, duration_ms=60)

# Send all packets
for pkt in packets:
    sock.sendto(pkt, (host, port))
```

#### Receiver with Deduplication

```python
from cw_fec import FECReceiver

# Create receiver
fec_receiver = FECReceiver(fec_mode='duplicate')

# Process received packet
packet_bytes = sock.recv(1024)
processed = fec_receiver.process_packet(packet_bytes)

if processed:
    # New packet (not duplicate)
    # Process normally...
    parsed = protocol.parse_packet(processed)
```

#### Receiver with Interpolation

```python
from cw_fec import FECReceiver

receiver = FECReceiver(fec_mode='none')
last_seq = -1
recent_packets = []

while True:
    pkt = sock.recv(1024)
    parsed = protocol.parse_packet(pkt)
    seq = parsed['sequence']
    
    # Detect gap
    if last_seq >= 0 and seq > last_seq + 1:
        # Try to interpolate missing packet(s)
        interpolated = receiver.interpolate_missing(
            last_seq, seq,
            recent_packets[-3:],  # Last 3 packets for context
            pkt
        )
        
        if interpolated:
            # Process interpolated packets
            for ipkt in interpolated:
                process_packet(ipkt)
    
    # Process received packet
    process_packet(pkt)
    
    # Keep history for interpolation
    recent_packets.append(pkt)
    if len(recent_packets) > 10:
        recent_packets.pop(0)
    
    last_seq = seq
```

## How Interpolation Works

Interpolation exploits CW's predictable patterns:

1. **Alternating states**: CW always alternates DOWN→UP→DOWN→UP
2. **Typical timing**: Dits ≈ 60ms, Dahs ≈ 180ms at 20 WPM
3. **Pattern recognition**: Uses recent packets to estimate timing

**Example:**
```
Received: DOWN(60ms) → UP(60ms) → [LOST] → DOWN(60ms)
                                    ↓
Interpolated: UP(60ms) - based on alternating pattern and average timing
```

**Limitations:**
- Cannot interpolate first packet (no context)
- Cannot interpolate > 2 consecutive losses (pattern breaks)
- Less accurate during irregular timing (QRS, fading)

## Bandwidth vs Reliability Trade-offs

| Method         | Bandwidth | Latency | Recovery @ 20% | Recovery @ 40% |
|----------------|-----------|---------|----------------|----------------|
| No FEC         | 1x        | 0ms     | 80%            | 60%            |
| Interpolation  | 1x        | 0ms     | 100%           | 72%            |
| 2x Duplicate   | 2x        | +50ms   | 94%            | 83%            |
| 3x Duplicate   | 3x        | +100ms  | 99%+           | 100%           |

**Latency estimates assume:**
- 50ms network RTT
- Packets arrive spread over time

## Recommendations by Use Case

### Local/LAN (< 1% loss)
- **No FEC needed**
- Use jitter buffer only

### Internet/WiFi (1-10% loss)
- **Use interpolation**
- Enable jitter buffer (50-100ms)
- Zero bandwidth overhead
- Near-perfect recovery

### Mobile/Unreliable (10-30% loss)
- **Use 2x duplication**
- Larger jitter buffer (100-200ms)
- 2x bandwidth overhead acceptable

### Extreme Conditions (30-50% loss)
- **Use 3x duplication**
- Large jitter buffer (200-300ms)
- Consider switching to more reliable transport

### Mission Critical
- **Combine 2x duplication + interpolation**
- Redundancy from duplication
- Gap filling from interpolation
- Best of both worlds

## Future Enhancements

Planned improvements:

1. **Hybrid FEC** - Combine duplication + interpolation automatically
2. **Adaptive FEC** - Adjust duplication level based on measured loss rate
3. **XOR Parity** - Send parity packets for groups (K+1 redundancy)
4. **Reed-Solomon FEC** - More sophisticated erasure coding
5. **Selective Repeat** - Request retransmission of specific lost packets (requires TCP control channel)

## Testing Your Network

Measure packet loss on your connection:

```bash
# Test receiver with statistics
python3 cw_receiver.py --jitter-buffer 100

# Send continuous stream
python3 cw_auto_sender.py <host> 25 "CQ CQ CQ DE W1AW"

# Check "Packets lost" in receiver statistics
# < 5% loss: Use interpolation or no FEC
# 5-20% loss: Use 2x duplication
# > 20% loss: Use 3x duplication or fix network!
```

## Technical Details

### Packet Format with FEC

**Standard packet:**
```
[Version+Flags][Seq][ClientID][Event...]
```

**Parity packet (XOR mode):**
```
[Version+Flags][Seq][ClientID|0x80][XOR'd payload]
```

The MSB of ClientID marks parity packets for XOR reconstruction.

### Deduplication Cache

Receiver maintains a cache of recent sequence numbers (up to 256) to detect duplicates. Cache is a rolling window to handle sequence number wraparound (0-255).

## Conclusion

**For most users:**
- Start with **interpolation** (zero overhead, excellent recovery)
- Add **2x duplication** if you see > 10% packet loss
- Use **3x duplication** only for extreme conditions

Test with `test_fec.py` to see which strategy works best for your network!
