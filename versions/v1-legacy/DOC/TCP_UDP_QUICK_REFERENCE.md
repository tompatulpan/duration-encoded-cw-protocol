# TCP vs UDP Quick Reference for CW Transmission

## At a Glance

| Aspect | TCP | UDP (Recommended) |
|--------|-----|-------------------|
| **Latency (no loss)** | 5-100ms | 50-150ms (includes buffer) |
| **Latency (5% loss)** | 100-500ms (unpredictable) | 100-150ms (consistent) |
| **Packet loss behavior** | ❌ Delays all subsequent packets | ✅ Creates gap, continues |
| **Jitter handling** | ⚠️ Uncontrolled TCP buffering | ✅ Controlled jitter buffer |
| **Manual keying** | ✅ Works (duration encoding) | ✅ Works (duration encoding) |
| **Implementation complexity** | Simple (no sequence numbers) | Medium (needs jitter buffer) |
| **NAT/Firewall** | ✅ Easy (connection-based) | ⚠️ May need port forwarding |

## Decision Tree

```
Do you have packet loss > 2%?
├─ YES → UDP with FEC (cw_receiver_fec.py)
└─ NO
   ├─ Firewall/NAT issues?
   │  ├─ YES → TCP (tcp_receiver.py)
   │  └─ NO → UDP (cw_receiver.py)
   └─ Need ultra-low latency (<50ms)?
      ├─ YES → UDP with small buffer (--jitter-buffer 20)
      └─ NO → UDP with standard buffer (--jitter-buffer 100)
```

## Common Scenarios

### Scenario 1: Local LAN Testing
**Best choice:** UDP with minimal buffer
```bash
python3 cw_receiver.py --jitter-buffer 20
python3 cw_usb_key_sender.py --host 192.168.1.100
```
**Why:** Low jitter, no packet loss, want minimal latency

---

### Scenario 2: Home Internet (Good Quality)
**Best choice:** UDP with standard buffer
```bash
python3 cw_receiver.py --jitter-buffer 100
python3 cw_usb_key_sender.py --host operator.example.com
```
**Why:** Some jitter, occasional loss, balanced latency/quality

---

### Scenario 3: Poor Internet (High Loss)
**Best choice:** UDP with FEC
```bash
python3 cw_receiver_fec.py --jitter-buffer 150
python3 cw_sender_fec.py --host operator.example.com
```
**Why:** Handles packet loss gracefully, maintains timing

---

### Scenario 4: Behind Firewall/NAT
**Best choice:** TCP (if UDP port forwarding not possible)
```bash
# TCP implementation (protocol-TCP directory)
python3 tcp_receiver.py --port 7356
python3 tcp_sender.py --host operator.example.com
```
**Why:** TCP NAT traversal is easier, connections are stateful

---

### Scenario 5: Contest/DX Operation
**Best choice:** UDP with FEC + moderate buffer
```bash
python3 cw_receiver_fec.py --jitter-buffer 150 --frequency 550
python3 cw_sender_fec.py --host dx-station.example.com
```
**Why:** Reliability matters, acceptable latency trade-off

---

## Manual Keying Configuration

**Both TCP and UDP use the same solution:**

### Sender Side
```python
# Measure duration at sender (not affected by network)
duration_ms = (current_time - last_event_time) * 1000
packet = create_packet(key_down, duration_ms)
send(packet)
```

### Receiver Side
```python
# Schedule relative to previous event end (immune to jitter)
if first_event:
    playout_time = now + buffer_delay
else:
    playout_time = last_event_end_time  # Relative timing!

schedule(playout_time, key_down, duration_ms)
last_event_end_time = playout_time + duration_ms / 1000.0
```

### Spacing Detection
```python
# Adaptive thresholds based on detected WPM
dit_threshold = (1200 / wpm) * 1.5
char_space_threshold = (1200 / wpm) * 2.0
word_space_threshold = (1200 / wpm) * 5.0
```

## Buffer Size Guidelines

| Network Type | Jitter | Recommended Buffer | Command |
|--------------|--------|-------------------|---------|
| Localhost | <5ms | 20ms | `--jitter-buffer 20` |
| LAN | 5-10ms | 50ms | `--jitter-buffer 50` |
| Good Internet | 20-50ms | 100ms | `--jitter-buffer 100` |
| Average Internet | 50-100ms | 150ms | `--jitter-buffer 150` |
| Poor Internet | 100-200ms | 200ms | `--jitter-buffer 200` |
| Satellite | 200ms+ | 300ms | `--jitter-buffer 300` |

**Rule of thumb:** Buffer = 2× expected jitter

## Performance Comparison

### Bandwidth Usage (20 WPM)
- **Both TCP and UDP:** ~2-3 KB/s
- **UDP with FEC:** ~4-6 KB/s (2× redundancy)
- **Overhead:** ~46 bytes per packet (IP+UDP+Ethernet)

### Latency Breakdown (Internet)
```
                    TCP                 UDP
Network:         50-100ms            50-100ms
Buffer:          (uncontrolled)      100ms (controlled)
Processing:      <5ms                <5ms
Audio:           20-40ms             20-40ms
────────────────────────────────────────────
Total (no loss): 70-145ms           170-245ms
Total (5% loss): 200-600ms          170-245ms ✓
                 (unpredictable)     (consistent)
```

**Key insight:** UDP has higher baseline latency but much more consistent behavior under packet loss.

## When TCP Might Be Better

1. **Firewall/NAT traversal is difficult**
   - UDP requires port forwarding
   - TCP is easier to configure

2. **Network has ZERO packet loss**
   - Perfect network → TCP has lower latency
   - Rare in practice (even LANs have occasional loss)

3. **Control messages (not real-time CW)**
   - Frequency changes
   - Mode settings
   - Text chat
   - Use hybrid: UDP for CW, TCP for control

## Migration Path: TCP → UDP

If you have TCP implementation and want to add UDP:

### Step 1: Add jitter buffer to TCP
```python
# Even TCP benefits from jitter buffer!
jitter_buffer = JitterBuffer(buffer_ms=30)

def on_tcp_receive(key_down, duration_ms):
    jitter_buffer.add_event(key_down, duration_ms, time.time())
```

### Step 2: Add UDP transport
```python
# Create UDP socket alongside TCP
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.bind(('0.0.0.0', 7355))

# Use same packet format and jitter buffer
```

### Step 3: Add sequence numbers (UDP)
```python
# Add to packet header
packet = struct.pack('BBB B', flags, seq, client_id, event_byte)
```

### Step 4: Test both protocols
```bash
# Compare side-by-side
python3 tcp_receiver.py --port 7356 &
python3 udp_receiver.py --port 7355 &
```

## Monitoring and Debugging

### Check Packet Loss
```bash
# Enable debug mode
python3 cw_receiver.py --debug --jitter-buffer 100

# Look for:
# [ERROR] Invalid state: got DOWN twice in a row  ← Packet loss
# [WARNING] Dropped late event                     ← Buffer underrun
```

### Measure Network Quality
```bash
# Ping test
ping -c 100 operator.example.com

# Look for:
# - Average latency (should be < 100ms for good CW)
# - Packet loss (should be < 2%)
# - Jitter (mdev should be < 50ms)
```

### Simulate Network Conditions
```bash
# Add artificial latency and loss (requires root)
sudo tc qdisc add dev eth0 root netem delay 50ms 20ms loss 2%

# Test receiver behavior under stress
python3 cw_receiver.py --jitter-buffer 150

# Remove when done
sudo tc qdisc del dev eth0 root
```

## Troubleshooting

### Symptom: Choppy audio, gaps in playback
**Diagnosis:** Packet loss or buffer underrun
**Fix:**
```bash
# Increase buffer
python3 cw_receiver.py --jitter-buffer 200

# Or use FEC
python3 cw_receiver_fec.py --jitter-buffer 150
```

### Symptom: Timing sounds wrong, elements stretched/compressed
**Diagnosis:** Using absolute timing instead of relative
**Fix:** Check receiver code uses relative timing:
```python
# CORRECT
playout_time = last_event_end_time

# WRONG - don't do this!
playout_time = arrival_time + buffer_delay
```

### Symptom: High latency (>500ms)
**Diagnosis:** Buffer too large or network issues
**Fix:**
```bash
# Reduce buffer
python3 cw_receiver.py --jitter-buffer 50

# Check network latency
ping operator.example.com
```

### Symptom: TCP receiver stalls occasionally
**Diagnosis:** Head-of-line blocking from packet loss
**Fix:** Switch to UDP:
```bash
python3 cw_receiver.py --jitter-buffer 100  # UDP version
```

## Code References

### UDP Implementation (Current)
```
test_implementation/
├── cw_protocol.py              ← Packet encoding/decoding
├── cw_receiver.py              ← UDP receiver with jitter buffer
├── cw_sender.py                ← Basic UDP sender
├── cw_usb_key_sender.py        ← Manual key input
├── cw_receiver_fec.py          ← FEC-enabled receiver
└── cw_protocol_fec.py          ← Reed-Solomon FEC
```

### TCP Implementation
```
protocol-TCP/test-implementation/
├── tcp_protocol.py             ← TCP-specific protocol (hypothetical)
├── tcp_receiver.py             ← TCP receiver
└── tcp_sender.py               ← TCP sender
```

## Key Takeaways

1. **UDP is better for real-time CW** due to predictable latency and better packet loss handling

2. **Manual keying works the same** for both TCP and UDP (duration encoding + relative timing)

3. **Jitter buffer size** is the key tuning parameter (50-200ms range)

4. **FEC helps with packet loss** but increases bandwidth 2× (still only ~5 KB/s)

5. **TCP might be easier** for NAT/firewall scenarios but has worse latency behavior

6. **Hybrid approach** (UDP for CW, TCP for control) gives best of both worlds

---

**Quick Start:**
1. Local testing: `python3 cw_receiver.py --jitter-buffer 20`
2. Internet use: `python3 cw_receiver.py --jitter-buffer 100`
3. Poor network: `python3 cw_receiver_fec.py --jitter-buffer 150`

**Full docs:**
- `TCP_UDP_COMPARISON.md` - Detailed analysis
- `MANUAL_KEYING_SOLUTIONS.md` - Timing and spacing solutions
- `JITTER_BUFFER_IMPLEMENTATION.md` - Buffer implementation details
