# Duration-Encoded CW Protocol (DECW)
**Real-Time Morse Code Transmission over UDP**

## What is DECW?

Duration-Encoded CW (DECW) is a low-latency protocol for transmitting Morse code over IP networks. Unlike text-based approaches, DECW transmits **raw key events with precise timing**, preserving the operator's natural keying rhythm and "fist".

**Key Innovation:** Each packet contains the **duration** of the event, not just state changes. This makes DECW robust against network jitter and packet loss, as each event is self-contained.

**Status:** 🚧 In development!  
This project is not production-ready. Features, structure, and documentation are subject to rapid change.

**Design Goal:** Simple setup in Linux (or Windows) using Python's cross-platform capabilities - no complex dependencies or compilation required. Just copy Python packages and run.

**Note:** Currently supports audio sidetone output. Physical key-jack output (for driving remote transmitters) is not yet implemented.

---

## Features

- ✅ **3-byte binary protocol** - Minimal overhead
- ✅ **Duration-encoded timing** - Each packet is self-contained
- ✅ **Adaptive jitter buffer** - Handles variable network latency
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

This is different from offset-based protocols which encode **time since last event**:

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

## Dependencies

- Python 3.14+
- pyserial (for USB key sender)
- pyaudio (for sidetone generation)
- numpy (for audio synthesis)

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

**Windows (untested but should work):**
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
python3 cw_auto_sender.py localhost 20 "CQ CQ CQ DE SM0ONR"

# Interactive line-by-line sender
python3 cw_interactive_sender.py localhost 25

# Hardware key (USB serial adapter on /dev/ttyUSB0 or COM3)
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0

# Hardware key with text-decoder
python3 cw_usb_key_sender_with_decoder.py localhost iambic-b 25 /dev/ttyUSB0

# Hardware key with FEC and decoder (for packet loss recovery)
python3 cw_usb_key_sender_with_decoder_fec.py localhost iambic-b 25 /dev/ttyUSB0
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

### Raspberry Pi GPIO Output

For driving physical transmitter keying circuits or relays on Raspberry Pi:

**Installation on Raspberry Pi:**
```bash
# RPi.GPIO is usually pre-installed on Raspberry Pi OS
# If needed, install with:
sudo apt install python3-rpi.gpio
# or: pip3 install RPi.GPIO

# For FEC support (packet loss recovery):
pip3 install reedsolo
```

**Basic Usage (without FEC):**
```bash
# Default: GPIO pin 17, active-high, 100ms jitter buffer
python3 cw_gpio_output.py

# Custom GPIO pin (BCM numbering)
python3 cw_gpio_output.py --pin 23

# For WAN/Internet use with larger buffer
python3 cw_gpio_output.py --buffer 200

# Active-low output (for some relay modules)
python3 cw_gpio_output.py --active-low

# Debug mode (show packet details and timing)
python3 cw_gpio_output.py --debug

# Show statistics every 10 seconds
python3 cw_gpio_output.py --stats

# Combine options
python3 cw_gpio_output.py --pin 23 --buffer 150 --active-low --debug --stats
```

**With FEC (Forward Error Correction for packet loss recovery):**
```bash
# Default: GPIO pin 17, active-high, 200ms jitter buffer (recommended for FEC)
python3 cw_gpio_output_fec.py

# Custom GPIO pin
python3 cw_gpio_output_fec.py --pin 23

# For poor network conditions with larger buffer
python3 cw_gpio_output_fec.py --buffer 250

# Active-low output
python3 cw_gpio_output_fec.py --active-low

# Debug mode
python3 cw_gpio_output_fec.py --debug

# Combine options
python3 cw_gpio_output_fec.py --pin 23 --buffer 200 --active-low --debug
```

**Hardware Connection:**
```
Raspberry Pi GPIO → Relay Module or Transistor → Transmitter Key Input

Simple transistor circuit:
GPIO Pin (e.g., 17) ──→ 1kΩ resistor ──→ NPN transistor base
                                         ├─ Collector → TX key input
                                         └─ Emitter → GND

For relay modules:
GPIO Pin → Relay IN
5V → Relay VCC
GND → Relay GND
```

**Pin Numbering:**
- Uses BCM (Broadcom) numbering scheme
- GPIO 17 = Physical pin 11
- GPIO 23 = Physical pin 16
- See [pinout.xyz](https://pinout.xyz) for complete pinout

**Jitter Buffer Recommendations:**
- Local network: 50-100ms
- Internet/WAN: 150-200ms
- Adjust based on network conditions

**Safety Notes:**
- GPIO pins output 3.3V @ max 16mA
- Use transistor/relay for driving transmitters
- Never connect GPIO directly to transmitter key input
- Add flyback diode across relay coils

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

The bandwidth required is very low (2-3 KB/s), so TCP’s overhead savings are not significant, but its latency penalty makes it unsuitable for real-time audio.

---



## Future Possibilities

Ideas for future development (not yet implemented):

1. **USB HID Paddle Interface (Recommended Alternative)**
   
   Cleaner alternative to USB serial adapters using Arduino as USB keyboard:
   
   ```
   Morse Paddle → Arduino (HID firmware) → USB → PC keyboard events

   ```
   
   **Advantages over serial adapters:**
   - No drivers needed (standard USB keyboard)
   - No serial port permissions required
   - Lower latency (<1ms vs 1-10ms)
   - Cross-platform consistency
   - Plug-and-play operation
   
   **Implementation:**
   - Arduino with ATmega32U4 chip (native USB support): https://docs.arduino.cc/hardware/micro/
   - Firmware: https://gitlab.com/dawszy-arduino-projects/usb-hid-cw-paddle
   - Python: Use `pynput` library (no root needed)
   - New script: `cw_hid_key_sender.py`
   
   **Signal flow:**
   ```
   Serial: Paddle → USB-Serial → /dev/ttyUSB0 → pyserial → cw_usb_key_sender.py
   HID: Paddle → Arduino HID → F13/F14 keys → pynput → cw_hid_key_sender.py
   ```


2. **Forward Error Correction**
   - Send redundant packets (2-3x)
   - Recover from packet loss
   - Trade-off: 100-200% bandwidth increase (still <1 Kbps total)

3. **Multi-Operator Support**
   - Relay server for CW "roundtables"
   - 3+ operators in same QSO


Inspired by:
- Protocol concept: Thomas Sailer (DL4YHF)
- Iambic keyer reference: Steve Haynal (n1gp/iambic-keyer)
- Ideas from Stu, KZ4LN


Happy CW operating!  
73 de SM0ONR


