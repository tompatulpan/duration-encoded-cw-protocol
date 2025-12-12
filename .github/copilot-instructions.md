# GitHub Copilot Instructions for Duration-Encoded CW Protocol

## Project Overview

This is a **Duration-Encoded CW (DECW) protocol** implementation for transmitting Morse code timing over networks (UDP and TCP). The protocol encodes CW key state changes (DOWN/UP) with precise timing information, enabling real-time Morse code communication over the internet.

## Core Architecture Principles

### Layered Module Structure

The codebase uses a **shared component architecture** to avoid duplication:

```
Core Layer:
  cw_protocol.py          → Base protocol (timing encoding/decoding)
    ├── Inherited by cw_protocol_tcp.py (TCP framing, duration-based)
    ├── Inherited by cw_protocol_tcp_ts.py (TCP framing, timestamp-based)
    └── Inherited by cw_protocol_fec.py (FEC error correction)

Shared Components Layer:
  cw_receiver.py          → Defines JitterBuffer and SidetoneGenerator
    ├── Imported by cw_receiver_tcp.py (duration-based scheduling)
    ├── Imported by cw_receiver_tcp_ts.py (timestamp-based scheduling)
    └── Imported by cw_receiver_fec.py

Applications:
  Senders:   cw_auto_sender*.py, cw_sender*.py
  Receivers: cw_receiver*.py
```

**Key Rule:** When adding features to `JitterBuffer` or `SidetoneGenerator`, modify them in `cw_receiver.py` only. All other receivers will automatically inherit the changes through imports.

## Protocol Design Guidelines

### 1. Packet Format and Timing

**UDP Packet Structure (3 bytes):**
```python
[sequence_number] [key_state] [duration_ms]
     1 byte         1 byte       1 byte (or 2 bytes for extended)
```

**Example packet breakdown:**
```
Packet for dit (48ms DOWN):
  Byte 0: 0x05      # Sequence number 5
  Byte 1: 0x01      # Key DOWN (0x00 = UP, 0x01 = DOWN)
  Byte 2: 0x30      # Duration 48ms (0x30 = 48 decimal)
```

**TCP Packet Structure (duration-based, length-prefix framing):**
```python
[length] [sequence_number] [key_state] [duration_ms]
 2 bytes      1 byte         1 byte       1-2 bytes
```

**TCP Timestamp Packet Structure (timestamp-based, burst-resistant):**
```python
[length] [sequence_number] [key_state] [duration_ms] [timestamp_ms]
 2 bytes      1 byte         1 byte       1-2 bytes     4 bytes
```

**Timestamp Protocol Design:**
- **Timestamp field:** 4 bytes, big-endian (`struct.pack('!I', ms)`)
- **Relative timing:** Milliseconds since `transmission_start` (sender tracks)
- **First packet:** Sets `transmission_start = time.time()`, timestamp = 0
- **Subsequent packets:** `timestamp = int((time.time() - transmission_start) * 1000)`
- **Receiver sync:** On first packet, `sender_timeline_offset = now - (timestamp / 1000.0)`
- **Absolute scheduling:** `playout_time = sender_timeline_offset + (timestamp / 1000.0) + buffer_ms / 1000.0`

**Why timestamp protocol:**
- Decouples arrival time from playout time (immune to packet bursts)
- Duration-based: Cumulative scheduling accumulates burst delays (queue buildup)
- Timestamp-based: Absolute time reference prevents cumulative delay
- Performance: Queue depth 2-3 (vs 6-7), scheduling variance ±1ms (vs ±50ms)

**Why length-prefix for TCP:**
- TCP is a stream protocol (no packet boundaries)
- Length header delimits messages in the stream
- Big-endian format: `struct.pack('!H', length)`

**Timing Encoding:**
- **0-255ms:** Direct encoding (1 byte, 1ms resolution)
- **256-65535ms:** Extended encoding (2 bytes, big-endian)
- **Common CW speeds (15-30 WPM):** Dit = 40-80ms, well within 1-byte range

**CW Timing Standards:**
```python
# WPM to timing conversion
dit_ms = 1200 / wpm

# Standard spacing (relative to dit length)
dit_length = 1 × dit_ms           # Dot element
dah_length = 3 × dit_ms           # Dash element
element_space = 1 × dit_ms        # Between dits/dahs in same character
letter_space = 3 × dit_ms         # Between characters
word_space = 7 × dit_ms           # Between words

# Example at 25 WPM (dit = 48ms):
dit = 48ms
dah = 144ms
element_space = 48ms
letter_space = 144ms
word_space = 336ms  # Triggers word space detection (>200ms)
```

**Packet Timing Philosophy:**
```python
# Each packet encodes: "Key was in STATE for DURATION"
# Duration is measured at sender, encoded in packet
# Receiver plays event at correct time using jitter buffer

# GOOD: Real-time transmission
send_packet(DOWN, 48)    # Send immediately
time.sleep(0.048)        # Wait actual duration
send_packet(UP, 48)      # Send next state

# BAD: Burst transmission (breaks timing)
send_packet(DOWN, 48)    # Send all at once
send_packet(UP, 48)      # Network receives packets in burst
send_packet(DOWN, 144)   # Timing distorted, audio artifacts
```

### 2. UDP vs TCP Decision Matrix

| Scenario | Use UDP | Use TCP | Use TCP+TS | Reason |
|----------|---------|---------|------------|--------|
| LAN | ✅ | ❌ | ❌ | Low latency, no packet loss |
| WiFi (good) | ✅ + buffer | ⚠️ + buffer | ✅ + buffer | TCP+TS best for WiFi bursts |
| WiFi (poor) | ❌ | ⚠️ + buffer | ✅ + buffer | Timestamps prevent queue buildup |
| Internet (good) | ✅ + buffer | ⚠️ + buffer | ✅ + buffer | UDP or TCP+TS work well |
| Internet (poor, >50ms jitter) | ❌ | ✅ + buffer | ✅ + buffer | TCP handles high jitter better |
| Packet loss 5-15% | ✅ + FEC | ❌ | ❌ | FEC can recover |
| Packet loss >15% | ❌ | ✅ | ✅ + TS | TCP retransmission needed |

**Default recommendations:**
- **LAN:** UDP (no buffer)
- **WiFi:** TCP with timestamps + 150ms buffer
- **Internet:** UDP + 100ms buffer, or TCP+TS + 150ms buffer

### 3. Sequence Numbers and Special Packets

**Sequence Number Handling:**
```python
# Sequence numbers wrap at 256 (1 byte)
sequence_number = (sequence_number + 1) % 256

# Used for:
# - Detecting packet loss (gaps in sequence)
# - Out-of-order detection
# - Statistics tracking
```

**End-of-Transmission (EOT) Packet:**
```python
# Special packet format:
[sequence_number] [0xFF] [0x00]
                  ↑ magic marker for EOT

# Receiver behavior on EOT:
# 1. Drain jitter buffer (wait for queued events)
# 2. Reset state validation (allow new transmission)
# 3. Clear watchdog timers
# 4. Print statistics
```

**EOT Timing in Sender:**
```python
# Send final event
send_packet(False, letter_space_ms)
time.sleep(letter_space_ms / 1000.0)

# Send EOT marker
send_eot_packet()

# Wait for receiver buffer to drain
time.sleep(1.0)  # Gives receiver time to play out buffered events
```

**Why the post-EOT delay:**
- Prevents overlapping transmissions
- Allows receiver's jitter buffer to fully drain
- Eliminates false "hitting ceiling" warnings
- Prevents audio desync between transmissions

### 4. Jitter Buffer Behavior

**Duration-Based Protocol (relative timing):**

```python
# Each event starts when the previous event ends
playout_time = self.last_event_end_time

# NOT absolute timing (would accumulate jitter)
# playout_time = arrival_time + buffer_ms  # WRONG
```

**Timestamp-Based Protocol (absolute timing):**

```python
# First packet: Synchronize to sender timeline
if self.sender_timeline_offset is None:
    self.sender_timeline_offset = time.time() - (timestamp_ms / 1000.0)

# Calculate sender's event time
sender_event_time = self.sender_timeline_offset + (timestamp_ms / 1000.0)

# Schedule with buffer
playout_time = sender_event_time + (self.buffer_ms / 1000.0)

# No relative timeline tracking (absolute reference)
```

**Key Difference - Scheduling Algorithm:**

**Duration-based: "Play when previous finishes"**
```python
# Cumulative chain - each event depends on previous
playout_time = self.last_event_end_time

# Example: 4 packets arrive in burst (all within 5ms)
Packet 1: DOWN 48ms  → playout at T+100ms, ends at T+148ms
Packet 2: UP 48ms    → playout at T+148ms, ends at T+196ms
Packet 3: DOWN 144ms → playout at T+196ms, ends at T+340ms
Packet 4: UP 48ms    → playout at T+340ms, ends at T+388ms

# Result: Queue depth = 4 events (all queued simultaneously)
#         Scheduled 388ms into future
#         Burst arrival accumulated into long chain
```

**Timestamp-based: "Play at sender's absolute time"**
```python
# Independent scheduling - each event has absolute reference
playout_time = sender_timeline_offset + (timestamp_ms / 1000.0) + buffer_ms

# Same 4 packets arrive in burst (all within 5ms)
Packet 1: ts=0ms   → playout at sender_T0 + 0ms + 150ms   (T+150ms)
Packet 2: ts=48ms  → playout at sender_T0 + 48ms + 150ms  (T+198ms)
Packet 3: ts=96ms  → playout at sender_T0 + 96ms + 150ms  (T+246ms)
Packet 4: ts=144ms → playout at sender_T0 + 144ms + 150ms (T+294ms)

# Result: Queue depth = 2-3 events (oldest plays out while new arrive)
#         Scheduled at consistent 150ms buffer target
#         Burst arrival doesn't create cumulative delay
```

**Why Timestamps Solve the Burst Problem:**
- Duration-based chains events together → burst creates long queue
- Timestamp-based uses sender's clock → each event independent
- WiFi/TCP bursts (4-5 packets in <5ms) don't accumulate delays
- Queue depth reduced from 6-7 to 2-3
- Scheduling variance reduced from ±50ms to ±1ms

**Performance Impact (WiFi Testing):**
- Duration-based: Queue 6-7 events, scheduling 200-480ms ahead (variable)
- Timestamp-based: Queue 2-3 events, scheduling 100-150ms (consistent)
- Audio artifacts eliminated (no "lengthening dah" from queue buildup)

**Word Space Detection (Critical for duration-based):**
- Gaps > 200ms indicate word spaces (not network jitter)
- Reset timeline to maintain buffer headroom
- Prevents false "late event" shifts
- **Not needed for timestamp protocol** (absolute timing)

**When modifying jitter buffer:**
- Duration-based: Preserve relative timing within characters/words
- Timestamp-based: Calculate absolute playout time from timestamp
- Only reset timeline on intentional gaps (word spaces, EOT) for duration-based
- Test with automated sender to verify word space handling

### 5. State Machine Validation

CW requires alternating DOWN/UP states:

```python
# Valid sequence
DOWN → UP → DOWN → UP

# Invalid (error)
DOWN → DOWN  # Error: got DOWN twice
UP → UP      # Error: got UP twice
```

**Exception:** After EOT or connection reset, state validation should reset.

### 6. Network Performance Expectations

**LAN (Local Area Network):**
- Latency: <5ms
- Jitter: <1ms
- Packet loss: 0%
- Configuration: No jitter buffer needed

**Good Internet:**
- Latency: 20-50ms
- Jitter: 5-20ms
- Packet loss: <1%
- Configuration: 50-100ms jitter buffer

**Poor Internet/Cellular:**
- Latency: 50-200ms
- Jitter: 20-100ms
- Packet loss: 1-5%
- Configuration: 150-200ms jitter buffer + TCP

**Extreme (Satellite/Congested):**
- Latency: >200ms
- Jitter: >100ms
- Packet loss: 5-15%
- Configuration: Use TCP, 200-300ms buffer, or FEC

## Code Style and Patterns

### 1. Audio Components

**Sidetone frequencies:**
- TX (sender): 600 Hz
- RX (receiver): 700 Hz
- Different frequencies help identify which station is keying

**Volume:** 0.3 (30%) - comfortable listening level

### 2. Debug Output

Use consistent formatting for timing information:

```python
print(f"[DEBUG] Arrival gap: {gap*1000:.1f}ms, Duration: {duration}ms, State: {'DOWN' if key_down else 'UP'}")
```

**Debug flags:**
- `--debug`: Verbose timing output
- `--debug-packets`: Show every packet (receiver)
- `--no-audio`: Disable audio for testing

### 3. Error Handling

**Network errors:** Graceful degradation
```python
try:
    packet = self.protocol.recv_packet()
    if packet is None:
        # Connection lost - handle reconnection
except socket.timeout:
    # Expected in non-blocking scenarios
    pass
```

**State errors:** Log but continue
```python
if invalid_state:
    self.state_errors += 1
    if not self.suppress_state_errors:
        print(f"[ERROR] Invalid state transition...")
    # Don't return - try to continue
```

### 4. Timing Precision

Always use `time.sleep()` for CW timing:

```python
# Send key DOWN event
self.send_event(True, duration_ms)

# Wait for the actual duration (simulate real-time keying)
time.sleep(duration_ms / 1000.0)

# Send key UP event
self.send_event(False, space_duration_ms)
```

**Why:** Ensures proper CW timing, prevents "bursting" all packets at once.

## Common Pitfalls to Avoid

### ❌ Don't: Send redundant UP packets for word spaces

```python
# WRONG: Creates state errors
send_event(False, dit_ms * 3)  # Letter space
send_event(False, dit_ms * 7)  # Word space - ERROR: UP twice!

# CORRECT: Just wait
send_event(False, dit_ms * 3)  # Letter space
time.sleep(dit_ms * 4 / 1000.0)  # Additional wait for word space
```

### ❌ Don't: Use absolute timing in jitter buffer

```python
# WRONG: Accumulates network jitter
playout_time = arrival_time + buffer_ms

# CORRECT: Relative timing preserves tempo
playout_time = self.last_event_end_time
```

### ❌ Don't: Ignore word space gaps

```python
# WRONG: Treats word spaces as late arrivals
if playout_time < now:
    shift_forward()  # Causes audio skips!

# CORRECT: Detect and reset
if arrival_gap > 0.2:  # 200ms = word space
    self.last_event_end_time = None  # Reset timeline
```

### ❌ Don't: Duplicate shared components

```python
# WRONG: Copy JitterBuffer to new receiver file
class MyReceiver:
    def __init__(self):
        # Duplicate JitterBuffer code here...

# CORRECT: Import from cw_receiver.py
from cw_receiver import JitterBuffer, SidetoneGenerator
```

## Testing Guidelines

### Manual Testing Checklist

When modifying timing or buffer code, test:

1. **Single character:** `python3 cw_auto_sender.py localhost 25 "E"`
2. **Word with spaces:** `python3 cw_auto_sender.py localhost 25 "CQ CQ"`
3. **Multiple transmissions:** Run sender twice in a row
4. **Various WPM:** Test 15, 20, 25, 30 WPM
5. **Buffer statistics:** Verify "Timeline shifts: 0"

### Debug Output Analysis

**Good statistics (LAN):**
```
Timeline shifts:  0          ← Perfect!
Max delay seen:   2.4ms      ← Low jitter
Buffer larger than needed    ← Expected on LAN
```

**Good statistics (Internet with buffer):**
```
Timeline shifts:  0          ← Perfect!
Max delay seen:   95.5ms     ← Within 100ms buffer
Buffer optimal               ← Well-sized
```

**Problem indicators:**
```
Timeline shifts:  5          ← Audio skips happening
  - After gaps:   0          ← NOT from word spaces (bug!)
Max delay seen:   205.5ms    ← Exceeds 200ms buffer (increase buffer)
```

## Adding New Features

### Adding a New Receiver Type

1. **Import shared components:**
```python
from cw_receiver import JitterBuffer, SidetoneGenerator
from cw_protocol import CWTimingStats
```

2. **Use consistent initialization:**
```python
if jitter_buffer_ms > 0:
    self.jitter_buffer = JitterBuffer(jitter_buffer_ms)
    self.jitter_buffer.start(self._playout_callback)
```

3. **Add command-line arguments:**
```python
parser.add_argument('--jitter-buffer', type=int, default=0)
parser.add_argument('--no-audio', action='store_true')
parser.add_argument('--debug', action='store_true')
```

### Adding a New Sender Type

1. **Choose protocol base:**
```python
from cw_protocol import CWProtocol          # UDP
from cw_protocol_tcp import CWProtocolTCP   # TCP
from cw_protocol_fec import CWProtocolFEC   # FEC
```

2. **Implement timing correctly:**
```python
# Send event
self.protocol.send_packet(key_down, duration_ms)

# Wait for duration (don't burst!)
time.sleep(duration_ms / 1000.0)
```

3. **Add sidetone if needed:**
```python
from cw_receiver import SidetoneGenerator

self.sidetone = SidetoneGenerator(600)  # TX frequency
self.sidetone.set_key(key_down)
```

## Documentation Standards

When adding features:

1. **Update README.md** with:
   - Usage examples
   - Command-line arguments
   - Performance characteristics

2. **Add inline comments** for:
   - Timing-critical sections
   - State machine transitions
   - Buffer behavior edge cases

3. **Update architecture diagrams** if:
   - Adding new protocol variants
   - Changing import dependencies
   - Adding shared components

## Performance Targets

- **LAN latency:** <5ms (without jitter buffer)
- **Internet latency:** <100ms (with 100ms jitter buffer)
- **Timing accuracy:** ±1ms for dit/dah durations
- **Packet loss recovery (FEC):** >90% at 10% loss rate
- **Timeline shifts:** 0 (no audio skips during normal operation)

## Version History Context

**Recent improvements (Dec 2025):**
- Word space detection in jitter buffer (eliminates timeline shifts)
- Adaptive buffer limits with warnings
- TCP version with proper framing and EOT handling
- Enhanced statistics with shift classification

When suggesting changes, preserve these improvements and maintain backward compatibility with existing UDP/FEC implementations.
