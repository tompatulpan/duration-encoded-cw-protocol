**Status:** 🚧 In development - Features and structure subject to change

# CW Protocol Test Implementation

This directory contains the complete Python reference implementation of the Duration-Encoded CW (DECW) protocol.

## Overview

DECW transmits Morse code timing over UDP or TCP networks. Each packet contains key state (DOWN/UP) and duration information, preserving precise timing despite network jitter.

---

## Technical Specification

### Packet Format

**UDP Packet (3 bytes):**
```
Byte 0: Sequence number (uint8_t, wraps at 256)
Byte 1: Key state (0 = UP/off, 1 = DOWN/on)
Byte 2: Duration in milliseconds (uint8_t, 0-255ms)
```

**TCP Packet (length-prefix framing):**
```
Bytes 0-1: Length (uint16_t, big-endian)
Byte 2: Sequence number
Byte 3: Key state
Byte 4: Duration (1-2 bytes depending on value)
```

**TCP Timestamp Packet:**
```
Bytes 0-1: Length (uint16_t, big-endian)
Byte 2: Sequence number
Byte 3: Key state
Bytes 4-5: Duration (1-2 bytes)
Bytes 6-9: Timestamp in milliseconds (uint32_t, big-endian)
```

**Example packet sequence for "S" (···) at 20 WPM:**
```
[0][DOWN][0]    - Initial state (start of transmission)
[1][UP][60]     - Was DOWN for 60ms (dit 1)
[2][DOWN][60]   - Was UP for 60ms (element space)
[3][UP][60]     - Was DOWN for 60ms (dit 2)
[4][DOWN][60]   - Was UP for 60ms (element space)
[5][UP][60]     - Was DOWN for 60ms (dit 3)
[6][UP][180]    - Was UP for 180ms (character space)
```

### Timing Standard

Based on PARIS standard (50 dits = 1 word):

```python
dit_duration_ms = 1200 / wpm
dah_duration_ms = 3 × dit_duration_ms
element_space_ms = dit_duration_ms
char_space_ms = 3 × dit_duration_ms
word_space_ms = 7 × dit_duration_ms
```

**Examples:**
- 20 WPM: dit=60ms, dah=180ms, char_space=180ms, word_space=420ms
- 25 WPM: dit=48ms, dah=144ms, char_space=144ms, word_space=336ms
- 30 WPM: dit=40ms, dah=120ms, char_space=120ms, word_space=280ms

### State Validation

The receiver validates packet sequences:
- **Valid:** DOWN → UP → DOWN → UP (alternating)
- **Invalid:** DOWN → DOWN (duplicate state)
- **Detected:** Packet loss via sequence number gaps

Errors are logged but don't stop playback. Statistics track error rates for network quality monitoring.

### Audio Synthesis

Simple sine wave generation at configurable frequency:

```python
# Generate tone
samples = sin(2π × frequency × time) × amplitude

# Apply 5ms rise/fall envelope to prevent clicks
samples[0:5ms] *= ramp_up
samples[-5ms:] *= ramp_down
```

**Implementation details:**
- Sample rate: 48kHz
- Format: 32-bit float
- Amplitude: 0.3 (30% of full scale)
- TX sidetone: 600 Hz (immediate local feedback)
- RX sidetone: 700 Hz (from network, buffered)

### Iambic Keyer Implementation

Built-in software keyer with three-state machine (IDLE, DIT, DAH):

**Mode A:** No paddle memory (stops when paddles released)  
**Mode B:** Paddle memory (remembers opposite paddle during element)

```
State transitions:
IDLE → DIT  (dit paddle pressed)
IDLE → DAH  (dah paddle pressed)
DIT  → DAH  (dah paddle pressed during dit)
DAH  → DIT  (dit paddle pressed during dah)
DIT  → IDLE (no paddles, no memory)
DAH  → IDLE (no paddles, no memory)
```

**Character spacing:** Automatically added after 14× dit duration of silence (adaptive EOT timeout).

### Performance Characteristics

| Metric | Value |
|--------|-------|
| **Packet size (UDP)** | 3 bytes |
| **Packet size (TCP)** | 3-5 bytes + length header |
| **Packet size (TCP+TS)** | 7-9 bytes + length header |
| **Network overhead (UDP)** | ~46 bytes total (IP+UDP+Ethernet+payload) |
| **TX latency** | < 1ms (local sidetone) |
| **RX latency (LAN)** | 5-20ms (network + minimal buffer) |
| **RX latency (Internet)** | 100-250ms (network + jitter buffer) |
| **Bandwidth (25 WPM)** | ~2-3 KB/s (~20 kbps) |
| **Jitter tolerance** | ±50ms typical, ±200ms tested |
| **Packet loss tolerance** | 5-10% (UDP), 0% (TCP with retransmission) |
| **Platform** | Linux, Windows, macOS (Python 3.7+) |

**Why UDP for Real-Time CW?**

UDP is preferred for low-latency applications:

- **Fire-and-forget**: Packets flow continuously without blocking
- **No head-of-line blocking**: One lost packet doesn't stall the stream
- **Timing preservation**: Jitter buffer handles timing; lost packets just create gaps
- **Real-time priority**: Network delivers packets as fast as possible

**TCP trade-offs:**

- **Pros:** 100% reliable delivery, works through more firewalls
- **Cons:** Retransmission delays (50-200ms+ per lost packet), head-of-line blocking
- **Use case:** High jitter networks where reliability > latency

**TCP+Timestamp advantages:**

- **Burst-resistant**: Absolute timing prevents cumulative delay from packet bursts
- **WiFi-optimized**: Handles 4-5 packet bursts without audio artifacts
- **Consistent scheduling**: ±1ms variance vs ±50ms for duration-based

---

## Files

### Core Protocol
- `cw_protocol.py` - Shared protocol implementation with timing encoding/decoding
- `cw_protocol_tcp.py` - **TCP wrapper with length-prefix framing and connection management**
- `cw_protocol_tcp_ts.py` - **TCP with absolute timestamps (burst-resistant timing)**
- `cw_protocol_udp_ts.py` - **UDP with absolute timestamps (low-latency + burst-resistant)**

### Receivers (UDP)
- `cw_receiver.py` - Terminal-based receiver with jitter buffer support (default: 0ms buffer)
- `cw_receiver_udp_ts.py` - **UDP receiver with timestamp synchronization (burst-resistant)**
- `cw_gpio_output.py` - Raspberry Pi GPIO output for physical key control (default: 100ms buffer)

### Receivers (TCP)
- `cw_receiver_tcp.py` - **TCP receiver with connection-based reliability (duration-based)**
- `cw_receiver_tcp_ts.py` - **TCP receiver with timestamp synchronization (burst-resistant)**

### Senders (UDP)
- `cw_auto_sender.py` - Automated sender (text to CW conversion)
- `cw_auto_sender_udp_ts.py` - **UDP automated sender with timestamps (burst-resistant)**
- `cw_interactive_sender.py` - Interactive sender (type-ahead with queue)
- `cw_usb_key_sender.py` - USB serial key interface with iambic keyer
- `cw_usb_key_sender_udp_ts.py` - **UDP USB key sender with timestamps (WiFi-optimized)**
- `cw_usb_key_sender_with_decoder.py` - USB key sender with CW-to-text decoder

### Senders (TCP)
- `cw_sender_tcp.py` - **TCP sender with automatic reconnection (manual keying)**
- `cw_auto_sender_tcp.py` - **TCP automated text-to-CW sender (duration-based)**
- `cw_auto_sender_tcp_ts.py` - **TCP automated sender with timestamps (burst-resistant)**
- `cw_usb_key_sender_tcp_ts.py` - **USB physical key sender with timestamps (WiFi-optimized)**

## Protocol Design Documentation

**How does manual keying work?**
- Duration encoded in packets (measured at sender)
- Relative timing on receiver (immune to network jitter)
- Adaptive spacing detection (handles variable operator timing)
- **Works the same for TCP and UDP** (application-layer solution)

See [Manual Keying Solutions](Doc/MANUAL_KEYING_SOLUTIONS.md) for details.

## Duration-Based vs Timestamp-Based Protocols

### Scheduling Algorithm Comparison

The key difference between TCP duration-based and TCP timestamp protocols is **how events are scheduled for playback**:

**Duration-Based (cumulative chain):**
```python
# Each event scheduled RELATIVE to previous event
playout_time = self.last_event_end_time  # Creates timing chain

# Example with packet burst (all arrive within 5ms):
Packet 1: DOWN 48ms  → schedule at T+100ms, ends at T+148ms
Packet 2: UP 48ms    → schedule at T+148ms, ends at T+196ms
Packet 3: DOWN 144ms → schedule at T+196ms, ends at T+340ms
Packet 4: UP 48ms    → schedule at T+340ms, ends at T+388ms

# Problem: Queue depth = 4 events, spans 388ms into future
# Burst arrival creates long event chain
```

**Timestamp-Based (absolute reference):**
```python
# Each event scheduled at ABSOLUTE sender time
playout_time = sender_timeline_offset + (timestamp_ms / 1000.0) + buffer_ms

# Same packet burst (all arrive within 5ms):
Packet 1: DOWN 48ms, ts=0ms   → schedule at sender_T0 + 0ms + 150ms   (T+150ms)
Packet 2: UP 48ms, ts=48ms    → schedule at sender_T0 + 48ms + 150ms  (T+198ms)
Packet 3: DOWN 144ms, ts=96ms → schedule at sender_T0 + 96ms + 150ms  (T+246ms)
Packet 4: UP 48ms, ts=144ms   → schedule at sender_T0 + 144ms + 150ms (T+294ms)

# Solution: Queue depth = 2-3 events, events stay near buffer target
# Independent scheduling prevents cumulative delay
```

### Why This Matters

**Duration-based:**
- "Play this when previous finishes" → burst creates chain
- WiFi bursts (4-5 packets in <5ms) build up queue depth 6-7
- Variable scheduling: 200-480ms ahead of target

**Timestamp-based:**
- "Play this at sender's time T" → burst doesn't accumulate
- Same WiFi bursts result in queue depth 2-3
- Consistent scheduling: 100-150ms (±1ms variance)

**Real-world impact:** Timestamp protocol eliminates "lengthening dah" artifacts caused by packet burst queue buildup over WiFi.

## Architecture and Code Dependencies

### Module Structure

The implementation uses a **layered architecture** with shared components to avoid code duplication:

```
┌─────────────────────────────────────────────────────────────┐
│                    CORE PROTOCOL LAYER                      │
│  • cw_protocol.py - Base protocol (encode/decode timing)   │
│    ├── CWProtocol (UDP base class)                         │
│    ├── CWTimingStats (statistics tracking)                 │
│    └── UDP_PORT constant (7355)                            │
└─────────────────────────────────────────────────────────────┘
                              ↓ (inherited by)
                              ↓
                 ┌────────────────────────┐
                 │  cw_protocol_tcp.py    │
                 │  • CWProtocolTCP       │
                 │  • CWServerTCP         │
                 │  • Length framing      │
                 │  • Connection mgmt     │
                 └────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   SHARED COMPONENTS LAYER                   │
│  • cw_receiver.py - Defines shared classes                 │
│    ├── JitterBuffer (timing smoothing logic)               │
│    └── SidetoneGenerator (audio generation)                │
└─────────────────────────────────────────────────────────────┘
                              ↓ (imported by)
                              ↓
                 ┌────────────────────────┐
                 │  cw_receiver_tcp.py    │
                 │  IMPORTS:              │
                 │  • JitterBuffer        │
                 │  • SidetoneGenerator   │
                 └────────────────────────┘
```

### Key Design Principles

**1. Single Source of Truth**
- `JitterBuffer` defined once in `cw_receiver.py`
- Used by all receiver types (UDP, TCP)
- One fix applies to all implementations

**2. Protocol Inheritance**
- `CWProtocol` provides base encoding/decoding
- `CWProtocolTCP` adds TCP framing and connection handling

**3. Component Reuse**
- `SidetoneGenerator` shared between receivers and senders
- Same audio generation for TX and RX sidetone
- Consistent 600Hz (TX) / 700Hz (RX) frequencies

### Import Dependencies by File

**Receivers:**
- `cw_receiver.py` → imports `cw_protocol.py` (base only)
- `cw_receiver_tcp.py` → imports `cw_protocol_tcp.py` + **JitterBuffer/SidetoneGenerator** from `cw_receiver.py`

**Senders:**
- `cw_auto_sender.py` → imports `cw_protocol.py` (UDP)
- `cw_auto_sender_tcp.py` → imports `cw_protocol_tcp.py` + **SidetoneGenerator** from `cw_receiver.py`
- `cw_sender_tcp.py` → imports `cw_protocol_tcp.py` (manual keying)

**Result:** Updating `cw_receiver.py` automatically improves all receivers and TCP senders!

### System Requirements
```bash
# For audio support (sidetone)
sudo apt-get install python3-pyaudio portaudio19-dev

# Or install in virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install pyaudio numpy
```

### Optional Dependencies
- **PyAudio** - Audio sidetone generation (receiver audio feedback)
- **numpy** - Audio signal processing (required with PyAudio)

Without these, the system runs in "visual only" mode (no audio).

## Usage

### Local/LAN Testing (No Packet Loss)

**UDP Version (default):**

**Terminal 1 (Receiver):**
```bash
python3 cw_receiver.py
```

**Terminal 2 (Sender):**
```bash
python3 cw_sender.py localhost
```

**TCP Version (recommended for high jitter networks):**

**Terminal 1 (Receiver):**
```bash
python3 cw_receiver_tcp.py
```

**Terminal 2 (Sender):**
```bash
python3 cw_sender_tcp.py localhost
```

**TCP Timestamp Version (best for WiFi / burst-prone networks):**

**Terminal 1 (Receiver):**
```bash
# 150ms buffer recommended for WiFi
python3 cw_receiver_tcp_ts.py --jitter-buffer 150
```

**Terminal 2 (Sender):**
```bash
python3 cw_auto_sender_tcp_ts.py localhost 25 "CQ CQ DE CALLSIGN"
```

**Buffer sizing for timestamp protocol:**
- LAN: 50-100ms (low jitter)
- WiFi (good): 150ms (handles most bursts)
- WiFi (poor): 200-250ms (eliminates all late events)

Press and hold **SPACE** to key down, release to key up.
Press **Q** to quit.

### Internet/WAN Usage

**UDP Version (with jitter buffer):**

**Receiver (enable jitter buffer for smooth timing):**
```bash
# Recommended for internet use
python3 cw_receiver.py --jitter-buffer 100
```

**Sender (from remote location):**
```bash
python3 cw_interactive_sender.py <receiver_public_ip> 7355
```

**TCP Version (better for high jitter/variable latency):**

**Receiver:**
```bash
# TCP handles retransmission, but jitter buffer still helps smooth timing
python3 cw_receiver_tcp.py --jitter-buffer 100
```

**Sender (from remote location):**
```bash
python3 cw_sender_tcp.py <receiver_public_ip> 7355
```

**TCP Timestamp Version (best for WiFi/burst-prone networks):**

**Receiver:**
```bash
# Timestamp protocol handles packet bursts better
python3 cw_receiver_tcp_ts.py --jitter-buffer 150
```

**Sender (from remote location):**
```bash
python3 cw_auto_sender_tcp_ts.py <receiver_public_ip> 25 "CQ CQ"
```

**Note:** Receiver must configure router port forwarding:
- UDP protocol: Port **7355** (duration-based)
- UDP timestamp: Port **7357** (burst-resistant)
- TCP duration-based: Port **7355**  
- TCP timestamp: Port **7356** (burst-resistant)

### Automated Text Sending

**UDP Version (duration-based):**
```bash
python3 cw_auto_sender.py localhost 25 "CQ CQ DE CALLSIGN"
```

**UDP Timestamp (burst-resistant, recommended for WiFi):**
```bash
python3 cw_auto_sender_udp_ts.py localhost 25 "CQ CQ DE CALLSIGN"
```

**TCP Duration-Based:**
```bash
python3 cw_auto_sender_tcp.py localhost 25 "CQ CQ DE CALLSIGN"
```

**TCP Timestamp-Based (recommended for WiFi):**
```bash
python3 cw_auto_sender_tcp_ts.py localhost 25 "CQ CQ DE CALLSIGN"
```

**Arguments:**
- `host` - Receiver IP address or hostname
- `wpm` - Words per minute (12-35 recommended)
- `text` - Text to send as CW

### Interactive Text Sending

**Standard mode (line-based):**
```bash
python3 cw_interactive_sender.py localhost
# Type message, press ENTER to send
```

**Buffered mode (character-by-character):**
```bash
python3 cw_interactive_sender.py localhost --buffered
# Each character sent immediately, queue display shown
```

### USB Physical Key

**UDP Version (duration-based):**

```bash
# Straight key
python3 cw_usb_key_sender.py localhost --mode straight

# Iambic paddles (Mode B recommended)
python3 cw_usb_key_sender.py localhost --mode iambic-b --wpm 25

# Bug (automatic dits, manual dahs)
python3 cw_usb_key_sender.py localhost --mode bug --wpm 20
```

**UDP Timestamp Version (burst-resistant, WiFi-optimized):**

```bash
# Straight key over WiFi
python3 cw_usb_key_sender_udp_ts.py 192.168.1.100 --mode straight

# Iambic paddles over WiFi
python3 cw_usb_key_sender_udp_ts.py 192.168.1.100 --mode iambic-b --wpm 25

# Bug over WiFi
python3 cw_usb_key_sender_udp_ts.py 192.168.1.100 --mode bug --wpm 20
```

**TCP Timestamp Version (WiFi with reliability):**

```bash
# Straight key over WiFi
python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode straight

# Iambic paddles over WiFi
python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode iambic-b --wpm 25

# Bug over WiFi
python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 --mode bug --wpm 20
```

Modes: `straight`, `bug`, `iambic-a`, `iambic-b`

**Receiver setup for USB key:**
```bash
# For UDP duration-based
python3 cw_receiver.py --jitter-buffer 50

# For UDP timestamp (WiFi)
python3 cw_receiver_udp_ts.py --jitter-buffer 100

# For TCP timestamp version (WiFi)
python3 cw_receiver_tcp_ts.py --jitter-buffer 150
```

## TCP vs UDP - When to Use Each

### UDP (Default - Recommended for Most Use Cases)
**Pros:**
- Lower latency (no retransmission delays)
- Graceful degradation (gaps instead of delays)
- No head-of-line blocking

**Cons:**
- Requires jitter buffer tuning for internet use
- No automatic packet recovery

**Best for:**
- LAN/local networks (0ms jitter buffer)
- Applications where timing consistency matters more than 100% reliability

### TCP Duration-Based (Better for High Jitter or Unreliable Networks)
**Pros:**
- Automatic retransmission (100% reliable delivery)
- No packet loss (connection-based)
- Better for networks with high jitter/variable latency
- Works through firewalls that block UDP

**Cons:**
- Higher latency (retransmission can cause delays)
- Head-of-line blocking (one delayed packet stalls stream)
- Still benefits from jitter buffer to smooth timing

**Best for:**
- High jitter networks (cellular, satellite, congested WiFi)
- Networks that block UDP
- When 100% reliability is required
- Testing/debugging (easier to trace connection issues)

### TCP Timestamp-Based (Best for WiFi / Burst-Prone Networks)
**Pros:**
- ✅ Burst-resistant (absolute timestamps, not cumulative timing)
- ✅ Lower queue depth (2-3 events vs 6-7 in duration-based)
- ✅ Consistent scheduling (±1ms variance vs ±50ms)
- ✅ All TCP benefits (retransmission, connection management)

**Cons:**
- +4 bytes per packet (timestamp overhead)
- Requires synchronized implementation (sender + receiver)

**Performance (WiFi testing):**
- Duration-based TCP: Queue depth 6-7, scheduling 200-480ms ahead (variable)
- Timestamp-based TCP: Queue depth 2-3, scheduling 100-150ms (consistent)
- Eliminates "lengthening dah" artifacts from packet bursts

**Best for:**
- WiFi networks (handles packet bursts gracefully)
- Real-time interactive keying over internet
- Any scenario where packet arrival is bursty
- Networks with variable latency spikes

### Quick Decision Guide

| Network Condition | Recommended Version |
|-------------------|---------------------|
| LAN/Local | UDP (no buffer) |
| Good Internet (<50ms jitter) | UDP + 100ms buffer |
| Poor Internet (>50ms jitter) | **TCP + 100ms buffer** |
| WiFi (good signal) | **TCP+TS + 150ms buffer** |
| WiFi (poor signal) | **TCP+TS + 200-250ms buffer** |
| Cellular/Satellite | **TCP + 150-200ms buffer** |
| Packet loss >5% | **TCP** |
| UDP blocked by firewall | **TCP or TCP+TS** |

See [TCP vs UDP Comparison](Doc/TCP_UDP_COMPARISON.md) for detailed analysis.

## Jitter Buffer (Enhanced)

For **internet/WAN use**, enable the jitter buffer to smooth out network timing variations:

```bash
# UDP version
python3 cw_receiver.py --jitter-buffer 100

# TCP duration-based version (still benefits from jitter buffer)
python3 cw_receiver_tcp.py --jitter-buffer 100

# TCP timestamp version (recommended for WiFi)
python3 cw_receiver_tcp_ts.py --jitter-buffer 150
```

### Recent Improvements (Dec 2025)

**Word Space Detection:**
- Automatically detects word spaces (gaps > 200ms)
- Resets timeline to maintain consistent buffer headroom
- Eliminates false "hitting ceiling" warnings
- Prevents audio skips during normal CW spacing

**Adaptive Buffer Limits:**
- Warns if buffer > 1000ms (excessive delay)
- Watchdog timeout scales with buffer size
- Graceful handling of large buffer configurations

**Result:** Zero timeline shifts during normal operation, smooth audio throughout entire transmission.

### Why Use Jitter Buffer?

**Network jitter** = variation in packet arrival times:
- Packets arrive at irregular intervals
- Without buffer: stuttering, uneven timing
- With buffer: smooth, consistent CW timing

**How it works:**
1. Packets arrive and queue in buffer
2. Buffer adds initial delay (e.g., 100ms)
3. Playout thread plays events at steady rate
4. Network jitter absorbed by buffer headroom

### Buffer Size Recommendations

| Network Type | Jitter Range | Recommended Buffer | Notes |
|--------------|--------------|-------------------|-------|
| LAN/Local | <1ms | **0ms** (disabled) | No buffer needed |
| Good Internet | 5-20ms | **50-100ms** | Standard setting |
| Poor Internet | 20-50ms | **100-150ms** | High jitter |
| Cellular/Satellite | 50-100ms+ | **150-200ms** | Variable latency |
| Extreme | >100ms | **200-300ms** | Use TCP instead |

**Maximum recommended:** 1000ms (system warns beyond this)

### Buffer Statistics

The receiver displays real-time statistics every 10 packets:

```
============================================================
NETWORK STATISTICS
============================================================
Buffer size:      200ms
Max delay seen:   4.5ms (2% of buffer)
Min delay seen:   195.5ms
Avg delay:        198.6ms (arrival-to-playout)
Timeline shifts:  0            ← Good! (no audio skips)
  - After gaps:   0            ← Manual keying pauses
Max queue depth:  4
Current queue:    0
Samples:          52

✓ Buffer larger than needed - could reduce to ~20ms
============================================================
```

**Key metrics:**
- **Timeline shifts: 0** = Perfect! No audio skips
- **Max delay seen** = Actual network jitter encountered
- **Buffer recommendation** = Suggests optimal size for your network

**Trade-off:** Higher buffer = smoother timing, but adds latency to QSO

See `Doc/JITTER_BUFFER_IMPLEMENTATION.md` for detailed configuration guide.

## Raspberry Pi GPIO Output

For driving physical key relays or transmitters, use the GPIO output on Raspberry Pi:

```bash
# Basic usage (GPIO 17, active-high)
python3 cw_gpio_output.py

# Custom pin and options
python3 cw_gpio_output.py --pin 23 --buffer 150 --debug

# Active-low (for some relay types)
python3 cw_gpio_output.py --active-low
```

**Hardware connections:**
- GPIO pin → Relay coil/Transistor/Opto-isolator
- GND → Common ground

See main README for complete hardware setup guide.
