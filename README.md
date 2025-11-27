# Duration-Encoded CW Protocol (DECW)
**Real-Time Morse Code Transmission over UDP**

## What is DECW?

Duration-Encoded CW (DECW) is a low-latency protocol for transmitting Morse code over IP networks. Unlike text-based approaches, DECW transmits **raw key events with precise timing**, preserving the operator's natural keying rhythm and "fist".

**Key Innovation:** Each packet contains the **duration** of the event, not just state changes. This makes DECW robust against network jitter and packet loss, as each event is self-contained.

**Status:** 🚧 In development!  
This project is not production-ready. Features, structure, and documentation are subject to rapid change.

**Design Goal:** Simple setup in Linux (or Windows) using Python's cross-platform capabilities - no complex dependencies or compilation required. Just install Python packages and run.

**Note:** Currently supports audio sidetone output. Physical key-jack output (for driving remote transmitters) is not yet implemented.

---

## Features

- ✅ **3-byte binary protocol** - Minimal overhead
- ✅ **Duration-encoded timing** - Each packet is self-contained
- ✅ **Adaptive jitter buffer** - Handles variable network latency (50-200ms)
- ✅ **Hardware key support** - Straight keys, bugs, iambic paddles (Mode A/B)
- ✅ **Zero-latency TX sidetone** - Hear yourself as you key
- ✅ **State validation** - Detects protocol errors
- ✅ **Network statistics** - Real-time analysis and recommendations
- ✅ **Cross-platform** - Python 3.14+ on Linux/Windows

---

## Why "Duration-Encoded"?

DECW packets contain the **exact duration** each event should last:

```
[seq=5][UP][180ms] = "Key up for exactly 180 milliseconds"
```

This is different from offset-based protocols (like netcw) which encode **time since last event**:

```
[seq=5][UP][60ms] = "Key went up 60ms after the previous event"
```

**Advantages of duration encoding:**
1. **Self-contained packets** - No dependency on previous packets
2. **Jitter tolerance** - Duration is preserved even if packet arrives late
3. **Simpler receiver** - Just schedule event for X milliseconds
4. **Better packet loss recovery** - Lost packet affects only one event
5. **Less accumulated delay** - Direct scheduling, no timeline reconstruction

---

## Quick Start

### Installation

**Linux (Fedora):**
```bash
# Install dependencies
sudo dnf install -y python3-pyaudio python3-pyserial python3-numpy portaudio

# Add user to dialout group for serial port access
sudo usermod -a -G dialout $USER
# Then log out and back in

# Create udev rule for USB serial devices (optional)
echo 'KERNEL=="ttyUSB[0-9]*", MODE="0666"' | sudo tee /etc/udev/rules.d/50-usb-serial.rules
sudo udevadm control --reload-rules
```

**Linux (Ubuntu/Debian):**
```bash
# Install dependencies
sudo apt install -y python3-pyaudio python3-serial python3-numpy portaudio19-dev

# Add user to dialout group
sudo usermod -a -G dialout $USER
# Then log out and back in
```

**Windows:**
```bash
# Install Python 3.14+ from python.org
# Then install dependencies:
pip install pyserial numpy

# For PyAudio (try in order):
pip install pyaudio
# If that fails, download precompiled wheel from:
# https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
pip install PyAudio‑0.2.11‑cp314‑cp314‑win_amd64.whl

# USB serial drivers usually auto-install
# Device will appear as COM3, COM4, etc.
```

### Basic Usage

```bash
# Start receiver
python3 cw_receiver.py

# Send automated text (in another terminal)
python3 cw_auto_sender.py localhost "CQ CQ CQ DE W1XYZ" 20

# Interactive line-by-line sender
python3 cw_interactive_sender.py localhost 25

# Hardware key (USB serial adapter on /dev/ttyUSB0 or COM3)
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0
```

### Common Options

```bash
# Adjust jitter buffer (for WAN connections)
python3 cw_receiver.py --buffer 200

# Disable receiver sidetone (use TX sidetone only)
python3 cw_receiver.py --no-sidetone

# Enable TX sidetone with custom frequency
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0 --sidetone-freq 700

# Debug mode (show packet details)
python3 cw_receiver.py --debug
```

## How It Works

### User Interface

The protocol provides three transmission modes:

1. **Automated Sender** (`cw_auto_sender.py`)
   - Converts text to Morse code automatically
   - Adjustable WPM (words per minute)
   - Sends complete messages with proper spacing

2. **Interactive Sender** (`cw_interactive_sender.py`)
   - Line-by-line text entry
   - Real-time conversion to CW
   - Queue multiple lines while sending

3. **USB Key Sender** (`cw_usb_key_sender.py`)
   - Physical straight key, bug, or iambic paddles
   - USB serial adapter (CTS/DSR pins as inputs)
   - Built-in iambic keyer (Mode A/B)
   - Optional TX sidetone for immediate audio feedback

**Receiver** (`cw_receiver.py`)
- UDP listener on port 7355
- Adaptive jitter buffer (50-200ms configurable)
- Audio sidetone generation (700Hz sine wave)
- Real-time statistics and error detection
- Preserves original timing from sender

### Hardware Setup

**USB Serial Adapter Pin Assignments:**

```
DB-9 or USB-TTL adapter:
├─ Pin 8 (CTS) ──→ Dit paddle (or straight key)
├─ Pin 6 (DSR) ──→ Dah paddle
└─ Pin 5 (GND) ──→ Common ground

For straight key: Connect key between CTS and GND
For iambic:      Connect dit paddle to CTS, dah paddle to DSR
```

**TX Sidetone:**
The USB key sender can generate zero-latency sidetone locally, eliminating the delay from the jitter buffer. This provides immediate audio feedback as you key.

```bash
# Enable TX sidetone (default 600 Hz)
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0

# Custom frequency
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0 --sidetone-freq 700

# Disable TX sidetone
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0 --no-sidetone
```

## Technical Specification

### Packet Format

Each DECW packet is exactly **3 bytes**:

```
Byte 0: Sequence number (uint8_t, wraps at 256)
Byte 1: Key state (0 = UP/off, 1 = DOWN/on)
Byte 2: Duration in milliseconds (uint8_t, 0-255ms)
```

**Example packet sequence for "S" (···) at 20 WPM:**
```
[0][DOWN][60]  - Dit 1
[1][UP][60]    - Element space
[2][DOWN][60]  - Dit 2
[3][UP][60]    - Element space
[4][DOWN][60]  - Dit 3
[5][UP][180]   - Character space (3 dits)
```

**Transport:**
- UDP port 7355
- No acknowledgments (fire-and-forget)
- Sequence numbers for packet loss detection

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

### Jitter Buffer Algorithm

DECW uses **relative timing** - each event is scheduled to start when the previous one ends:

```python
# Simple scheduling model
event_start_time = last_event_end_time
event_end_time = event_start_time + duration_from_packet
play_audio(event_start_time, duration_from_packet)
last_event_end_time = event_end_time
```

**Adaptive buffer sizing:**
- Monitors packet arrival jitter
- Tracks manual keying gaps vs. network-induced delays
- Recommends buffer size based on observed conditions
- Typical: 50ms (LAN) to 200ms (WAN)

**Initial buffer delay:**
When the first packet arrives, the receiver waits to build up buffer headroom before playing. This delay is only noticeable at the start of a new transmission (after EOT or long silence).

**Buffer Recommendations:**
- Localhost: 20-50ms
- LAN: 50-100ms
- Internet: 100-200ms
- Default: 100ms

### State Validation

The receiver validates packet sequences:
- **Valid:** DOWN → UP → DOWN → UP (alternating)
- **Invalid:** DOWN → DOWN (duplicate state)
- **Detected:** Packet loss via sequence number gaps

Errors are logged but don't stop playback. Statistics track error rates for network quality monitoring.

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

### Audio Synthesis

Simple sine wave generation at configurable frequency (default 600-700 Hz):

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
- TX sidetone: PyAudio callback, 512-sample buffer
- RX sidetone: Synchronized with jitter buffer playout

### Performance Characteristics

| Metric | Value |
|--------|-------|
| **Packet size** | 3 bytes |
| **Network overhead** | ~46 bytes total (IP+UDP+Ethernet+payload) |
| **TX latency** | < 1ms (local sidetone) |
| **RX latency (localhost)** | 50-100ms (buffer + audio) |
| **RX latency (Internet)** | 150-250ms (network + buffer + audio) |
| **Bandwidth (30 WPM)** | ~2.4 KB/s (~19.6 kbps) |
| **Overhead ratio** | 15:1 (46 bytes total per 3 bytes CW data) |
| **Jitter tolerance** | ±50ms typical, ±200ms tested |
| **Packet loss tolerance** | 5-10% (depends on buffer size) |
| **Platform** | Linux, Windows, macOS (Python 3.14+) |

**Why UDP (not TCP)?**

Despite the high overhead ratio, UDP is the correct choice because CW is a **real-time protocol** where timing matters more than reliability:

**TCP problems for real-time CW:**
- **Head-of-line blocking**: One lost packet stalls ALL subsequent packets until retransmission
- **Retransmission delay**: Adds full RTT latency (50-200ms+) to playback
- **Defeats jitter buffer**: TCP's reliability mechanism conflicts with timing-based buffering
- **Old data is worthless**: By the time TCP retransmits, the audio should have already played

**UDP advantages:**
- **Fire-and-forget**: Packets flow continuously without blocking
- **Timing preservation**: Jitter buffer handles timing; lost packets just create gaps
- **State validation**: Detects packet loss (logs errors) but continues playback
- **Duration preservation**: Even with lost packets, received events play at correct duration
- **Real-time priority**: Network delivers packets as fast as possible without waiting

**Packet loss handling:**
- Lost packets detected via sequence numbers
- State validation logs errors (DOWN-DOWN or UP-UP sequences)
- Playback continues with wrong gap timing but correct element durations
- Manual correction by operator (natural for CW operating)
- Better than TCP's complete playback stall

The bandwidth is so low (2-3 KB/s) that TCP's overhead savings are meaningless, but TCP's latency penalty is **unacceptable** for real-time audio.

---

## Comparison to netcw (W8BSD)

Both DECW and netcw transmit **binary key events** over UDP for low-latency CW.

### Packet Format Comparison

| Feature | DECW (This Protocol) | netcw |
|---------|---------------------|-------|
| **Packet size** | 3 bytes | 4 bytes |
| **Format** | `[seq][state][duration_ms]` | `[seq][event][time_msb][time_lsb]` |
| **Timing model** | Absolute duration | Relative time offset |
| **Byte order** | Native | Network (big-endian) |
| **Character spacing** | Explicit (long UP packet) | Implicit (silence) |
| **Status packets** | No | Yes (types 2,3,4 for sync) |

### Timing Model Difference

**DECW (Duration-Encoded):**
```
[DOWN][60ms] = "Key down for 60 milliseconds"
[UP][180ms] = "Key up for 180 milliseconds (character space)"

Each packet is self-contained.
```

**netcw (Offset-Encoded):**
```
[DOWN][0ms] = "Key down NOW"
[UP][60ms] = "Key up 60ms after previous event"

Requires timeline reconstruction from offsets.
```

### Robustness on Jittery Networks

**DECW is more robust** because:

| Scenario | DECW | netcw |
|----------|------|-------|
| **Jitter tolerance** | ✅ Duration preserved in packet | ⚠️ Requires timeline reconstruction |
| **Packet loss** | ✅ Self-contained events | ❌ Breaks timing chain |
| **Out-of-order packets** | ✅ Sequence sorts it out | ❌ Offset calculation fails |
| **Late packets** | ✅ Buffer handles it | ⚠️ Must recalculate timeline |
| **Receiver complexity** | ✅ Simple: schedule for X ms | ⚠️ Complex: calculate when to start |
| **Accumulated delay** | ✅ Less (direct scheduling) | ⚠️ More (timeline reconstruction) |

**Example: Packet Loss Recovery**

```
DECW:
[seq=0][DOWN][60ms]  ← Arrives
[seq=1][UP][60ms]    ← LOST!
[seq=2][DOWN][60ms]  ← Arrives
→ State validation detects error: [ERROR] Invalid state: got DOWN twice in a row (error #1)
→ Receiver plays both DOWNs with correct durations
→ Gap between them is wrong, but element timing preserved

netcw:
[seq=0][DOWN][0ms]   ← Arrives at T=0
[seq=1][UP][60ms]    ← LOST!
[seq=2][DOWN][60ms]  ← Arrives at T=120
→ Receiver doesn't know when UP should have occurred
→ Timeline reconstruction fails completely
```

### When to Use Each

**Use DECW for:**
- Real-time QSOs over WAN/internet
- Hardware key operation (straight, bug, iambic)
- Networks with variable latency or packet loss
- Training/contesting with authentic timing
- Preserving operator's "fist" characteristics

**Use netcw for:**
- Low-jitter LANs
- When status sync is needed (types 2,3,4)
- Established netcw infrastructure

---

## Dependencies

- Python 3.14+
- pyserial (for USB key sender)
- pyaudio (for sidetone generation)
- numpy (for audio synthesis)

## File Structure

```
test_implementation/
├── cw_protocol.py           # Core protocol encoder/decoder
├── cw_auto_sender.py         # Automated text-to-CW sender
├── cw_interactive_sender.py  # Interactive line-by-line sender
├── cw_usb_key_sender.py      # Hardware key/paddle interface
├── cw_receiver.py            # Receiver with jitter buffer
└── README.md                 # This file
```

## Platform Support

DECW is written in Python and runs on any platform with Python 3.14+:

**✅ Linux** (Fedora, Ubuntu, Debian, Arch, etc.)
- Native PyAudio/PortAudio support
- Serial ports: `/dev/ttyUSB0`, `/dev/ttyACM0`
- Recommended for production use

**✅ Windows** (7, 8, 10, 11)
- PyAudio via precompiled wheels
- Serial ports: `COM3`, `COM4`, etc.
- Full feature parity with Linux

**✅ macOS** (untested but should work)
- PyAudio via Homebrew
- Serial ports: `/dev/cu.usbserial-*`

**Design Goal:** Simple setup with minimal dependencies. No compilation required - just Python and a few packages.

## Examples

### Example 1: Local Testing
```bash
# Terminal 1: Start receiver
python3 cw_receiver.py

# Terminal 2: Send a message
python3 cw_auto_sender.py localhost "CQ CQ DE W1XYZ K" 20
```

### Example 2: WAN Connection
```bash
# Remote station (receiver)
python3 cw_receiver.py --buffer 200

# Local station (sender with hardware key)
python3 cw_usb_key_sender.py remote.example.com iambic-b 25 /dev/ttyUSB0 --sidetone-freq 700
```

### Example 3: Training Setup
```bash
# Trainer sends practice text
python3 cw_interactive_sender.py localhost 15

# Student listens without sidetone (receive-only)
python3 cw_receiver.py --buffer 50
```

## Future Enhancements

### Planned Features

1. **Physical Key-Jack Output**
   - Drive relay/keying circuit for transmitter
   - Convert received CW to hardware keying
   - Complete remote station control

2. **Multi-Operator Relay Server**
   - Support CW "jam" sessions with 3+ operators
   - Room/channel management
   - Optional callsign identification

3. **Recording & Playback**
   - Save QSO sessions
   - Replay for training
   - Export to audio/text

4. **Web Interface**
   - Browser-based receiver (WebRTC)
   - Real-time operator list
   - Chat/spotting integration

## License

Public domain / MIT - Use as you wish.

## Contributors

Implementation: 2025

Inspired by:
- Protocol concept: Thomas Sailer (DL4YHF)
- Iambic keyer reference: Steve Haynal (n1gp/iambic-keyer)

## 73!

Happy CW operating!  
73 de SM0ONR

Questions? Issues? PRs welcome!
