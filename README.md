# Duration-Encoded CW Protocol (DECW)

**Real-Time Morse Code Transmission over IP Networks**

## What is DECW?

Duration-Encoded CW (DECW) is a protocol for transmitting Morse code timing information over IP networks (UDP/TCP) intended prio for **remote control**. Unlike text-based approaches, DECW transmits **raw key events with precise timing**, preserving the operator's natural keying rhythm and "fist".

Each packet contains the **duration** of the event, not just **state changes**. This makes DECW robust against network jitter, as each event is self-contained and can be scheduled independently.

**Status:** 🚧 In development - Features and structure subject to change

**Design Goal:** Simple, cross-platform setup using Python - no complex dependencies or compilation required.

---

## Core Concepts

### Why "Duration-Encoded"?

Each packet describes a state transition with the duration of the previous state:

```
[seq=5][UP][180ms] = "Key was DOWN for 180 milliseconds"
```

**How it works:**
- Manual keying: When key changes state, send packet with new state + previous state's duration
- Example: Press key → starts timer → release key (180ms later) → send `[UP][180ms]`
- Receiver: Play each state for its specified duration

**Benefits:**
- Self-contained packets (no dependency on previous packets)
- Jitter tolerant (duration preserved even if packet arrives late)
- Simpler receiver (just schedule event for X milliseconds)
- Better packet loss recovery (lost packet affects only one event)

### Protocol Variants

The project includes multiple implementations optimized for different network conditions:

- **UDP** - Low latency, best for LAN
- **UDP+Timestamps** - Burst-resistant timing
- **TCP** - Reliable delivery, better for high jitter
- **TCP+Timestamps** - Burst-resistant timing
- **WebSocket** - Browser-based implementation

See [VERSIONS.md](VERSIONS.md) for the project version map. Detailed documentation:

- v2 (active, modular): [`apps/`](apps/) - test senders/receivers using the modular structure
- v1 (legacy, archived): [`versions/v1-legacy/`](versions/v1-legacy/)
- Web platform (separate repo): [`../web_platform_tcp/`](../web_platform_tcp/)

---

## Quick Start

The active v2 implementation is the modular structure at the repository root
(`protocol/`, `buffer/`, `audio/`, `keyer/`, `apps/`). The complete legacy
implementation with all variants is in [`versions/v1-legacy/`](versions/v1-legacy/).

### Installation

**Linux (Fedora):**
```bash
sudo dnf install -y python3-pyaudio python3-pyserial python3-numpy portaudio
sudo usermod -a -G dialout $USER  # For serial port access, then log out/in
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install -y python3-pyaudio python3-serial python3-numpy portaudio19-dev
sudo usermod -a -G dialout $USER  # For serial port access, then log out/in
```

### Basic Usage (v2, modular)

```bash
# Start receiver (terminal 1)
python3 apps/test_receiver_udp.py --jitter-buffer 50

# Send automated text (terminal 2)
python3 apps/test_sender_udp.py localhost 20 "CQ CQ CQ DE SM5ABC"

# UDP with timestamps (burst-resistant)
python3 apps/test_receiver_udp_ts.py --jitter-buffer 150
python3 apps/test_sender_udp_ts.py localhost 20 "CQ CQ"

# TCP with timestamps (WiFi-optimized)
python3 apps/test_receiver_tcp_ts.py --jitter-buffer 150
python3 apps/test_sender_tcp_ts.py localhost 20 "CQ CQ"
```

### Basic Usage (v1, legacy)

```bash
cd versions/v1-legacy/

# Start receiver
python3 cw_receiver.py

# Send automated text (in another terminal)
python3 cw_auto_sender.py localhost 20 "CQ CQ CQ DE SM5ABC"

# Interactive line-by-line sender
python3 cw_interactive_sender.py localhost 25

# Hardware key (USB serial adapter)
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0
```

### Network Jitter Buffer

For internet/WAN use, enable the jitter buffer to smooth network timing variations:

```bash
# Recommended for internet use
python3 cw_receiver.py --jitter-buffer 100

# For TCP timestamp version (WiFi-optimized)
python3 apps/test_receiver_tcp_ts.py --jitter-buffer 150
```

**Buffer sizing:**
- LAN: 0ms (no buffer needed)
- Good Internet: 50-100ms
- Poor Internet/WiFi: 150-200ms

---

## Implementation Overview

### Terminal-Based Python Implementation

The [`versions/v1-legacy/`](versions/v1-legacy/) directory contains the complete legacy Python reference implementation with:

- **Multiple protocol variants** (UDP, UDP+timestamps, TCP, TCP+timestamps)
- **Automated senders** (text-to-CW conversion)
- **Interactive senders** (line-by-line keying)
- **Physical key support** (USB serial adapters, iambic keyers)
- **GPIO output** (Raspberry Pi - drive transmitter relays)
- **Detailed documentation** (protocol specs, tuning guides)

See [versions/v1-legacy/README.md](versions/v1-legacy/README.md) for complete technical documentation.

### Web Platform Implementation

The [`../web_platform_tcp/`](../web_platform_tcp/) directory (separate project, one level up) contains an experimental browser-based implementation:

- **WebSocket-based** (JSON event protocol)
- **Multi-user rooms** (practice with multiple operators)
- **Real-time CW decoder** (Morse to text)
- **Web Audio API** (sidetone generation)
- **No installation required** (works in any modern browser)

See [../web_platform_tcp/README.md](../web_platform_tcp/README.md) for web platform details.

---

## Hardware Setup
Here we have a coupleof options.

### Serial or USB-interface alternatives
- USB HID interface
- USB HID (Vail adapter)
- Serial Interface

### USB HID Physical Key Interface

The **[`../USB_HID/`](../USB_HID/)** directory (separate project, one level up) contains a production-ready hardware interface:

- **Seeedstudio XIAO SAMD21** microcontroller
- **USB HID Keyboard protocol** (works on Linux/Windows/macOS)
**Quick Start:**
```bash
# 1. Upload firmware (Arduino IDE)
cd ../USB_HID/xiao_samd21_hid_key/
# Open .ino file, select Seeeduino XIAO board, upload

# 2. Wire your paddles
#    XIAO D2 → Dit paddle → GND
#    XIAO D1 → Dah paddle → GND

# 3. Run sender
cd ../
python3 cw_xiao_hidraw_sender.py <receiver_ip> --wpm 25 --debug

# 4. Run receiver
cd ../protocol/apps/
python3 test_receiver_tcp_ts.py --jitter-buffer 150
```

**See [../USB_HID/README.md](../USB_HID/README.md) for complete setup guide, troubleshooting, and technical details.**

### Vail adapter hardware
See this - https://vailadapter.com/

**Note** Will require the same firmware as the HID interface.

### USB Serial Adapter for Physical Keys

**Pin assignments:**
```
DB-9 or USB-TTL adapter:
├─ Pin 8 (CTS) ──→ Dit paddle (or straight key)
├─ Pin 6 (DSR) ──→ Dah paddle
└─ Pin 5 (GND) ──→ Common ground
```
For straight key: Connect key between CTS and GND  
For iambic: Connect dit paddle to CTS, dah paddle to DSR

### Interfaces features together with the Sender-software
- **Iambic-keyer**
- **Straight key mode**
- **Real-time sidetone**

### Raspberry Pi GPIO Output

For driving physical transmitter keying circuits:

```bash
cd versions/v1-legacy/

# Basic usage (GPIO 17, active-high)
python3 cw_gpio_output.py

# Custom GPIO pin with buffer
python3 cw_gpio_output.py --pin 23 --buffer 150

```

**Hardware connection:** GPIO Pin → Relay/Transistor → Transmitter Key Input

See [versions/v1-legacy/README.md](versions/v1-legacy/README.md) for complete hardware setup details.

**Note** Serial interfaces can behave porly depending on supported sampling speed!

---

## Documentation

### Protocol Specifications

- [TCP-TS Protocol Specification](Doc/TCP_TS_PROTOCOL_SPECIFICATION.md) - TCP with timestamps for WiFi/burst-resistant timing
- [Timestamp Protocol Example](Doc/TIMESTAMP_PROTOCOL_EXAMPLE.md) - Detailed timing trace examples

### Implementation Documentation

Complete technical documentation is in the implementation directories:

- **[versions/v1-legacy/README.md](versions/v1-legacy/README.md)** - Python implementation guide (legacy)
  - Protocol specifications (packet format, timing)
  - Protocol variants (UDP, TCP)
  - Usage examples and command-line options
  - Jitter buffer tuning and configuration
  - Hardware setup (GPIO, USB serial)
  - Network performance and testing
  
- **[../web_platform_tcp/README.md](../web_platform_tcp/README.md)** - Web platform guide
  - WebSocket implementation
  - Browser requirements
  - Deployment instructions
  - Multi-user room features

---

## Project Status & Future Ideas

**Currently implemented:**
- ✅ 3-byte UDP protocol
- ✅ TCP variants (duration-based and timestamp-based)
- ✅ Jitter buffer with word space detection
- ✅ Hardware key support (USB serial)
- ✅ USB HID paddle interface
- ✅ Iambic keyer
- ✅ Audio sidetone
- ✅ GPIO output (Raspberry Pi)
- ✅ Real-time CW decoder
- ✅ Web platform (experimental)

**Future possibilities:**
- ESP32 HID variant (TinyUSB issues to resolve)
- Multi-operator relay server
- Additional error correction methods

---

## Acknowledgments

Inspired by:
- Protocol concept: Wolfgang Buescher (DL4YHF)
- Iambic keyer reference: Steve Haynal (n1gp/iambic-keyer)
- USB HID inspired by the Vail-CW adapter project - https://github.com/Vail-CW
- Ideas and testing: Stu (KZ4LN)
- Testing: Fabian Kurz (DJ5CW/SO5CW)

---

**Happy CW operating!**  
73 de SM0ONR
