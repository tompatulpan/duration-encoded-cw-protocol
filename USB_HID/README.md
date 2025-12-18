# USB HID CW Keyer Solutions

Hardware solution for connecting CW paddles to the Duration-Encoded CW Protocol over networks and web platform.

## XIAO SAMD21 USB HID Keyer ⭐ **RECOMMENDED**

A compact USB HID device that appears as a keyboard to the host PC. The microcontroller reads paddle inputs and presents them as USB keyboard key presses, which Python software reads and transmits over TCP-TS.

### Why XIAO SAMD21?
- **Proven working design** - Based on [Vail-CW adapter](https://github.com/Vail-CW/vail-adapter)
- **Built-in USB** - No USB-serial adapter needed
- **Standard HID keyboard** - Works with Arduino Keyboard library
- **Tiny form factor** - 18mm × 21mm
- **Low cost** - ~$5-8 from Seeed or AliExpress

### Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                   XIAO SAMD21                               │
│                                                             │
│  ┌────────────┐    ┌──────────────┐   ┌─────────────┐     │
│  │   GPIO     │ →  │   Firmware   │ → │  USB HID    │     │
│  │  Inputs    │    │  (Arduino)   │   │  Keyboard   │     │
│  │  (2 pins)  │    │  Keyboard    │   │             │     │
│  └────────────┘    │  library     │   └─────────────┘     │
│       ↑            └──────────────┘          ↓            │
│  Dit/Dah paddles                        USB cable          │
│                                                ↓            │
└─────────────────────────────────────────────────────────────┘
                                                 ↓
                                   ┌────────────────────────┐
                                   │   Host PC (Linux)      │
                                   │                        │
                                   │  Python sender reads   │
                                   │  keyboard events via   │
                                   │  /dev/hidraw* or       │
                                   │  /dev/input/event*     │
                                   │                        │
                                   │  TCP-TS → Network      │
                                   └────────────────────────┘
```

### Bill of Materials

| Component | Model | Price | Source |
|-----------|-------|-------|--------|
| Microcontroller | Seeed XIAO SAMD21 | $5-8 | Seeed, AliExpress |
| Paddles | User-supplied | - | Existing HAM equipment |
| USB cable | USB-C | $2 | Standard cable |
| Optional: Piezo | 5V buzzer | $1 | For local sidetone |
| **Total** | | **~$7-10** | Minimal setup |

### Pin Wiring

```
XIAO SAMD21 Pinout:

   ┌─────────────────────┐
   │  Seeed XIAO SAMD21  │
   │                     │
   │  D2 (PA08) ─────────── Dit paddle input (internal pull-up)
   │  D1 (PA04) ─────────── Dah paddle input (internal pull-up)
   │  GND ───────────────── Common ground to paddles
   │  5V ────────────────── Optional piezo for local sidetone
   │  USB-C ─────────────── Connect to host PC
   └─────────────────────┘

Paddle Wiring:
  Dit paddle: Normally-open switch between D2 and GND
  Dah paddle: Normally-open switch between D1 and GND
  Common: All paddles share common ground
  
  Internal pull-ups keep pins HIGH when open
  Closed = pin reads LOW (active-low logic)
```

### Firmware (Arduino)

**File:** `xiao_samd21_hid_key/xiao_samd21_hid_key.ino`

**Key features:**
- Uses Arduino `Keyboard.h` library (NOT custom HID descriptors)
- Sends `KEY_LEFT_CTRL` (dit) and `KEY_RIGHT_CTRL` (dah)
- Appears as standard USB HID keyboard device
- Comprehensive Serial debug output (115200 baud)

**Upload instructions:**
1. Install Arduino IDE 2.x
2. Add Seeeduino SAMD boards: Tools → Board Manager → "Seeed SAMD Boards"
3. Select: Tools → Board → Seeed SAMD → "Seeed XIAO M0"
4. Open `xiao_samd21_hid_key.ino`
5. Click Upload (firmware ~35KB, 13% of flash)
6. Verify: `lsusb -v -d 2886:802f | grep bInterfaceClass` shows "3 HID"

**Debugging:**
- Serial output available at `/dev/ttyACM0` (115200 baud)
- Shows heartbeat, button events, key press/release
- Close Arduino Serial Monitor before reading in terminal

### Python Senders (Host PC)

Two Python senders are available, each for different use cases:

#### 1. TCP-TS Sender (LAN/Direct Connections)

**File:** `cw_xiao_sender_tcp_ts.py`

**Use case:** Direct connection to local receiver (LAN, same network)

**Features:**
- Reads XIAO via raw `/dev/hidraw*` access (robust, no hidapi bugs)
- TCP-TS protocol with timestamps (burst-resistant)
- Iambic Mode B keyer (default, configurable to Mode A or straight key)
- 600Hz TX sidetone with local audio feedback
- Automatic device detection by VID:PID (2886:802f)
- **Shared code:** Imports protocol modules from `../test_implementation`

**Usage:**
```bash
# Iambic Mode B (default), 20 WPM
python3 cw_xiao_sender_tcp_ts.py <receiver_ip>

# Iambic Mode A, 25 WPM
python3 cw_xiao_sender_tcp_ts.py <receiver_ip> --mode iambic-a --wpm 25

# Straight key mode
python3 cw_xiao_sender_tcp_ts.py <receiver_ip> --mode straight

# Manual device specification
python3 cw_xiao_sender_tcp_ts.py <receiver_ip> --device /dev/hidraw2

# Disable local sidetone
python3 cw_xiao_sender_tcp_ts.py <receiver_ip> --no-audio

# Debug mode (shows HID reports and timing)
python3 cw_xiao_sender_tcp_ts.py <receiver_ip> --debug
```

#### 2. WebSocket Sender (Web Platform / Internet)

**File:** `cw_xiao_sender_web.py`

**Use case:** Connect to web-based CW decoder via WebSocket relay (Cloudflare Workers)

**Features:**
- WebSocket JSON protocol (compatible with browser decoder)
- Connects to internet relay server (e.g., `cw-studio-relay.workers.dev`)
- Room-based multi-user support
- Handshake confirmation (waits for browser to be ready)
- Timestamp protocol for precise timing
- 600Hz TX sidetone with local audio feedback
- Iambic keyer and straight key modes

**Usage:**
```bash
# Basic connection (requires callsign)
python3 cw_xiao_sender_web.py --url cw-studio-relay.data4-9de.workers.dev --callsign SM5ABC

# With WPM setting
python3 cw_xiao_sender_web.py --url cw-studio-relay.data4-9de.workers.dev --callsign SM5ABC --wpm 25

# Straight key mode
python3 cw_xiao_sender_web.py --url cw-studio-relay.data4-9de.workers.dev --callsign SM5ABC --mode straight

# Disable local sidetone
python3 cw_xiao_sender_web.py --url cw-studio-relay.data4-9de.workers.dev --callsign SM5ABC --no-audio

# Different modes
--mode straight      # Straight key
--mode iambic-a      # Iambic Mode A
--mode iambic-b      # Iambic Mode B (default)
```

**URL formats accepted:**
- `cw-studio-relay.data4-9de.workers.dev` (adds wss:// automatically)
- `wss://cw-studio-relay.data4-9de.workers.dev` (full URL)

**Installation (WebSocket sender only):**
```bash
pip3 install websockets
```

**Connection handshake:**
The web sender implements a handshake protocol:
1. Connects to WebSocket server
2. Sends `join` message with callsign and room
3. Waits for `joined` or `echo` confirmation
4. Only starts transmission after confirmation (prevents lost events)

This eliminates the need to refresh the browser - the sender waits for the decoder to be ready!

### Code Dependencies
### Code Dependencies

Both senders use `sys.path.insert(0, '../test_implementation')` to import shared modules:
- `cw_protocol_tcp_ts.py` - TCP timestamp protocol (TCP-TS sender only)
- `cw_receiver.py` - Sidetone generator (both senders)
- `xiao_hid_reader.py` - Shared XIAO HID reader (both senders)

This avoids duplicating protocol code. The folder structure must be:
```
protocol/
├── test_implementation/      ← Shared protocol modules
│   ├── cw_protocol_tcp_ts.py
│   └── cw_receiver.py
└── USB_HID/                  ← XIAO senders
    ├── cw_xiao_sender_tcp_ts.py  (LAN/direct)
    ├── cw_xiao_sender_web.py     (web platform)
    └── xiao_hid_reader.py         (shared reader)
```

### Installation

**Common dependencies (both senders):**
```bash
pip3 install pyaudio numpy
```

**WebSocket sender only:**
```bash
pip3 install websockets
```

**TCP-TS sender only:**
No additional dependencies (uses standard library sockets)

### First-time Setup (Linux permissions)

```bash
# Add udev rule (recommended for persistent access)
echo 'KERNEL=="hidraw*", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="802f", MODE="0666", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/99-xiao.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Replug the XIAO, then test
python3 cw_xiao_sender_tcp_ts.py localhost --debug
```

### Which Sender to Use?

| Scenario | Use | Why |
|----------|-----|-----|
| **LAN/same network** | `cw_xiao_sender_tcp_ts.py` | Lower latency, direct TCP connection |
| **Internet/remote** | `cw_xiao_sender_web.py` | Browser-based decoder, no firewall issues |
| **Multi-user practice** | `cw_xiao_sender_web.py` | Room-based sharing via web platform |
| **Local practice** | `cw_xiao_sender_tcp_ts.py` | Simpler, no internet required |
| **Demo/public display** | `cw_xiao_sender_web.py` | Share link, anyone can watch/decode |

### Troubleshooting

**Device not found:**
```bash
# Check XIAO is connected
lsusb | grep 2886

# Find hidraw device
ls -l /dev/hidraw*

# Check device info
udevadm info /dev/hidraw1 | grep -E 'ID_VENDOR_ID|ID_MODEL_ID'
```

**Permission denied:**
```bash
# Apply udev rule (permanent fix)
sudo tee /etc/udev/rules.d/99-xiao.rules << EOF
KERNEL=="hidraw*", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="802f", MODE="0666", TAG+="uaccess"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger

# Or temporarily use sudo
sudo python3 cw_xiao_sender_tcp_ts.py localhost
```

**Web sender - connection timeout:**
- Check URL is correct (with or without `wss://` prefix)
- Verify WebSocket relay is running
- Open browser to decoder page first (sender waits for handshake)

**No audio/sidetone:**
- Check PipeWire/PulseAudio is running
- Try `--no-audio` to disable if not needed
- Install audio dependencies: `pip3 install pyaudio`

### Why This Design Works

**Previous attempt (FAILED):**
- Custom HID descriptor with `HID().AppendDescriptor()`
- `HID().SendReport()` appeared to work (returned 2 bytes)
- Linux rejected USB enumeration - only showed CDC serial interfaces
- `lsusb` showed `bInterfaceClass 2` (Communications), not `3` (HID)

**Current approach (WORKING):**
- Arduino `Keyboard.h` library (built into SAMD core)
- Standard USB HID keyboard descriptor (handled by library)
- `Keyboard.press(KEY_LEFT_CTRL)` / `Keyboard.release()`
- Linux accepts HID interface automatically
- Proven by [Vail-CW adapter](https://github.com/Vail-CW/vail-adapter) (MIT license)

**Technical details:**
- SAMD21 has native USB support, but custom HID descriptors are problematic
- Arduino Keyboard library provides proper USB HID keyboard implementation
- Works identical to commercial USB keyboards
- No driver installation needed on Linux/Windows/macOS

---

## Additional Documentation

- **HARDWARE.md** - Detailed hardware setup and wiring diagrams
- **SENDERS.md** - Comprehensive sender documentation and comparison
- **TESTING.md** - Testing procedures and validation
- **XIAO_TROUBLESHOOTING.md** - Common issues and solutions
- **CHANGELOG.md** - Version history and updates

## Quick Start

1. **Flash firmware** to XIAO SAMD21 (see HARDWARE.md)
2. **Connect paddles** to D1 (dah) and D2 (dit), common to GND
3. **Install dependencies:** `pip3 install pyaudio numpy websockets`
4. **Run sender:**
   - LAN: `python3 cw_xiao_sender_tcp_ts.py <receiver_ip>`
   - Web: `python3 cw_xiao_sender_web.py --url <websocket_url> --callsign <your_call>`
5. **Start keying!**

---

## ESP32 Standalone Keyer (Future)

An ESP32-based standalone keyer is planned for future development. It would eliminate the need for a PC by implementing the keyer and network protocol directly in firmware.

**Status:** Design only, not yet implemented. XIAO solution (above) is currently recommended.

See `esp32_cw_keyer.ino` for firmware skeleton and design notes.

---

## License

MIT License - See LICENSE file in project root

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   ESP32-WT32-ETH01                          │
│                                                             │
│  ┌────────────┐    ┌──────────────┐   ┌─────────────┐     │
│  │   GPIO     │ →  │   Iambic     │ → │  TCP-TS     │     │
│  │  Inputs    │    │   Keyer      │   │  Encoder    │     │
│  │  (2 pins)  │    │  (Software)  │   │             │     │
│  └────────────┘    └──────────────┘   └─────────────┘     │
│       ↑                                       ↓            │
│  Dit/Dah paddles                        Ethernet PHY       │
│                                                ↓            │
└─────────────────────────────────────────────────────────────┘
                                                 ↓
                                        ┌────────────────┐
                                        │  Network       │
                                        │  (LAN/WAN)     │
                                        └────────────────┘
                                                 ↓
                                 ┌───────────────────────────┐
                                 │   Receiver (PC/RPi)       │
                                 │                           │
                                 │  TCP → Jitter Buffer →    │
                                 │  Audio/GPIO               │
                                 └───────────────────────────┘
```

**Replaces:** PC + USB-serial adapter + Python sender  
**Advantages:** Simpler, portable, lower latency, ~$15 total cost

## Hardware Requirements

### Recommended: WT32-ETH01 Module (~$8)

- **CPU:** ESP32 (240MHz dual-core)
- **RAM:** 520KB SRAM
- **Flash:** 4MB
- **Ethernet:** Native LAN8720 PHY (10/100 Mbps)
- **WiFi:** 802.11 b/g/n (backup connectivity)
- **GPIO:** 6+ available pins
- **Form factor:** 18mm × 42mm (compact)
- **Power:** USB 5V or 3.3V direct

**Alternative:** ESP32-Ethernet-Kit (~$25) - More GPIOs, easier breadboarding

### Bill of Materials

| Component | Model | Price | Notes |
|-----------|-------|-------|-------|
| Microcontroller | WT32-ETH01 | ~$8 | AliExpress, Amazon |
| Paddles | User-supplied | - | Existing HAM equipment |
| Piezo buzzer | Generic 5V | $1 | Optional sidetone |
| Resistors | 100Ω, 1kΩ | $0.50 | Current limiting |
| USB cable | Micro-USB | $2 | Power only |
| Ethernet cable | CAT5e/6 | $3 | Network connection |
| Case | 3D printed | $2-5 | Optional enclosure |
| **Total** | | **~$15** | Minimal setup |

## Pin Wiring

### WT32-ETH01 Pinout

```
ESP32-WT32-ETH01 Module:

   ┌─────────────────────┐
   │  WT32-ETH01         │
   │                     │
   │  GPIO 2 ──────────── Dit paddle input (internal pull-up)
   │  GPIO 4 ──────────── Dah paddle input (internal pull-up)
   │  GPIO 12 ─────────── Sidetone PWM output (optional)
   │  GPIO 15 ─────────── Status LED (optional)
   │  GND ───────────────── Common ground
   │                     │
   │  [LAN8720 PHY]      │
   │  RJ45 ──────────────── Ethernet cable to network
   │                     │
   │  Micro-USB ─────────── 5V power input
   └─────────────────────┘

Paddle Wiring (simple interface):

  Dit paddle: Normally-open switch between GPIO 2 and GND
  Dah paddle: Normally-open switch between GPIO 4 and GND
  Common: All paddles share common ground
  
  Internal pull-ups keep pins HIGH when open
  Closed = pin reads LOW (active-low logic)
```

### Optional Sidetone Circuit

**Option 1: Piezo Buzzer (simplest)**
```
GPIO 12 → 100Ω resistor → Piezo buzzer (+) → GND
```
Works directly, no amplifier needed, adequate volume.

**Option 2: Speaker with Transistor Amplifier**
```
GPIO 12 → 1kΩ resistor → NPN base (2N2222)
Transistor collector → Speaker (8Ω) → +5V
Transistor emitter → GND
```
More volume, better for passive speakers.

**Option 3: DAC + Audio Amplifier Module (best quality)**
```
GPIO 25 (DAC) → PAM8403 module → Speaker
```
Cleaner sine wave, adjustable volume, ~$1 amplifier board.

## Firmware Features

### Current Implementation Status

- [ ] **Phase 1: Straight Key Mode** (MVP)
  - [ ] GPIO paddle input (1ms polling)
  - [ ] TCP-TS packet encoding
  - [ ] Ethernet/WiFi connectivity
  - [ ] Basic status LED
  
- [ ] **Phase 2: Iambic Keyer**
  - [ ] Mode A (no paddle memory)
  - [ ] Mode B (paddle memory during elements)
  - [ ] Bug mode (auto dits, manual dahs)
  - [ ] WPM configuration (15-30 WPM)
  
- [ ] **Phase 3: Configuration & Polish**
  - [ ] Web UI for settings (WiFi AP mode)
  - [ ] EEPROM storage (receiver IP, WPM, mode)
  - [ ] Button interface (speed adjust, mode select)
  - [ ] PWM sidetone (600Hz)
  - [ ] OTA firmware updates

### Protocol: TCP-TS (Timestamp-Based)

**Packet format:** 9 bytes per event
```
┌────────────┬────────────┬───────────┬─────────────┬──────────────┐
│  Length    │  Sequence  │  State    │  Duration   │  Timestamp   │
│  (2 bytes) │  (1 byte)  │ (1 byte)  │ (1-2 bytes) │  (4 bytes)   │
├────────────┼────────────┼───────────┼─────────────┼──────────────┤
│ Big-endian │  0-255     │ 0x00/0x01 │ Big-endian  │  Big-endian  │
│   uint16   │  Wrapping  │ UP/DOWN   │ uint8/16    │   uint32 ms  │
└────────────┴────────────┴───────────┴─────────────┴──────────────┘
```

**Protocol semantics:**
- **key_down=true**: Transition TO DOWN, was UP for `duration_ms` (spacing)
- **key_down=false**: Transition TO UP, was DOWN for `duration_ms` (element)
- **timestamp_ms**: Milliseconds since transmission start (sender's clock)
- **duration_ms**: Duration of PREVIOUS state (self-contained packets)

**Why duration + timestamp:**
- Duration: Self-contained packets, robust to loss
- Timestamp: Absolute time reference, burst-resistant scheduling
- Combined: Queue depth 2-3 events (vs 6-7 without timestamps)

**Receiver compatibility:**
- Works with existing `cw_receiver_tcp_ts.py` (port 7356)
- 100-150ms jitter buffer recommended for WiFi
- <5ms latency on wired LAN

## Development Setup

### Arduino IDE (Recommended)

1. **Install Arduino IDE** (v2.x)
   - Download: https://www.arduino.cc/en/software

2. **Add ESP32 Board Support**
   - File → Preferences → Additional Board Manager URLs:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
   - Tools → Board → Boards Manager → Search "ESP32" → Install

3. **Select Board**
   - Tools → Board → ESP32 Arduino → ESP32 Dev Module
   - Tools → Upload Speed → 115200

4. **Required Libraries** (all built-in)
   - `ETH.h` - Ethernet support
   - `WiFi.h` - WiFi support
   - `Preferences.h` - EEPROM storage
   - `WebServer.h` - Configuration UI (optional)

### Alternative: MicroPython

```bash
# Flash MicroPython firmware
esptool.py --chip esp32 erase_flash
esptool.py --chip esp32 write_flash -z 0x1000 esp32-micropython.bin

# Upload code via ampy
pip install adafruit-ampy
ampy --port /dev/ttyUSB0 put main.py
```

## Usage

### Quick Start

1. **Power on** - Connect USB 5V or 3.3V power
2. **First boot** - Device creates WiFi AP "CW-Keyer-Setup"
3. **Configure** - Connect to AP, browse to 192.168.4.1
4. **Enter settings:**
   - Receiver IP address (e.g., 192.168.1.100)
   - Receiver port (default: 7356)
   - WPM speed (default: 20)
   - Keyer mode (Straight/Iambic A/B)
5. **Save & reboot** - Device connects to network
6. **Start receiver** on PC/Raspberry Pi:
   ```bash
   python3 test_implementation/cw_receiver_tcp_ts.py --jitter-buffer 150
   ```
7. **Key CW** - Hear sidetone on receiver (700Hz)

### Configuration Options

**Runtime settings** (stored in EEPROM):
- Receiver IP address & port
- WPM speed (15-30 typical)
- Keyer mode (Straight/Bug/Iambic A/B)
- Paddle swap (dit/dah reversal)
- Sidetone enable/disable
- WiFi credentials

**Access via:**
- Web UI (WiFi AP mode): http://192.168.4.1
- Serial console: 115200 baud, send commands

### LED Status Indicators

| LED Pattern | Meaning |
|-------------|---------|
| Solid ON | Connected to receiver |
| Slow blink (1Hz) | Connecting/searching |
| Fast blink (5Hz) | Configuration mode |
| Brief flashes | TX activity (key down) |
| OFF | No power or error |

---

## Comparison: XIAO vs ESP32

| Feature | XIAO SAMD21 ⭐ | ESP32 Ethernet |
|---------|----------------|----------------|
| **Implementation** | ✅ Working now | 📋 Design only |
| **Cost** | $7-10 | $15-20 |
| **Requires PC** | Yes (USB host) | No (standalone) |
| **Network** | Via PC (WiFi/LAN) | Native Ethernet/WiFi |
| **Keyer mode** | SW (Python) | FW (on-chip) |
| **Portability** | Laptop + device | Device only |
| **Latency** | 5-10ms (USB+SW) | 2-5ms (direct) |
| **Configuration** | Command-line args | Web UI + EEPROM |
| **Complexity** | Simple (1 chip) | Moderate (FW dev) |
| **Use case** | Home station | Portable/field |

**Recommendation:**
- **Start with XIAO** - Works now, proven design, easy setup
- **Consider ESP32** - Future upgrade for portable/standalone operation

## Performance Specifications

### Timing Characteristics (XIAO Implementation)

| Metric | XIAO Value | Requirement | Status |
|--------|-------------|-------------|--------|
| Paddle polling rate | 1ms | <5ms | ✅ Excellent |
| USB HID latency | <2ms | <10ms | ✅ Excellent |
| Python processing | <1ms | <5ms | ✅ Excellent |
| TCP send latency | 2-5ms | <10ms | ✅ Good |
| Total latency | 5-10ms | <20ms | ✅ Excellent |
| Timing resolution | 1ms | 1ms | ✅ Perfect |
| Iambic keyer accuracy | ±1ms | ±5ms | ✅ Excellent |

### Network Performance

| Scenario | Latency | Jitter Buffer | Status |
|----------|---------|---------------|--------|
| LAN (wired) | <5ms | Not needed | ✅ Perfect |
| WiFi (good) | 20-50ms | 100-150ms | ✅ Good |
| Internet (good) | 50-100ms | 150-200ms | ✅ Acceptable |
| Internet (poor) | >100ms | 200-300ms | ⚠️ Marginal |

### Resource Usage (XIAO SAMD21)

| Resource | Used | Available | Percentage |
|----------|------|-----------|------------|
| Flash | 35KB | 256KB | 13% |
| SRAM | <8KB | 32KB | <25% |
| GPIO | 2 pins | 11 pins | Plenty |
| Power | <100mA | USB 500mA | Adequate |

### Resource Usage (ESP32, estimated)

| Resource | Used | Available | Headroom |
|----------|------|-----------|----------|
| Flash | ~500KB | 4MB | 87% free |
| SRAM | ~70KB | 520KB | 86% free |
| GPIO | 4 pins | 20+ pins | Plenty |
| Power | <150mA | - | USB adequate |

## Testing

### Test Receivers

The main codebase provides these test receivers:

1. **Audio Sidetone** (PC/Mac/Linux)
   ```bash
   python3 test_implementation/cw_receiver_tcp_ts.py --jitter-buffer 150
   ```
   Plays 700Hz tone, prints decoded text

2. **GPIO Keying** (Raspberry Pi)
   ```bash
   python3 test_implementation/cw_gpio_output_tcp_ts.py --jitter-buffer 150
   ```
   Keys GPIO pin for transmitter PTT

3. **Web Decoder** (Browser)
   - Start: `cd web_platform_tcp && python3 worker/local_server.py`
   - Open: http://localhost:8787
   - Real-time text decoding in browser

### Test Procedure

1. **Hardware test** - LED blink, verify GPIO reads
2. **Network test** - Ping receiver from ESP32
3. **Protocol test** - Send single packet, verify reception
4. **Straight key** - Toggle GPIO, observe audio on receiver
5. **Timing test** - Send test pattern "PARIS", measure WPM
6. **Iambic test** - Full keyer state machine validation
7. **Stress test** - Rapid keying, check queue depth

### Debug Output

Serial console (115200 baud) shows:
```
[INFO] Connecting to 192.168.1.100:7356...
[INFO] Connected! Transmission start.
[TX] DOWN duration=0ms timestamp=0ms seq=0
[TX] UP duration=48ms timestamp=48ms seq=1
[TX] DOWN duration=48ms timestamp=96ms seq=2
...
[INFO] Packets sent: 42, Bytes: 378
```

## Comparison to PC-Based System

| Aspect | PC + USB-Serial | Standalone ESP32 |
|--------|----------------|------------------|
| Components | PC, USB adapter, paddles | ESP32, paddles |
| Latency | USB (1-2ms) + OS overhead | Direct GPIO (<1ms) |
| Portability | Requires PC | Standalone box |
| Power | PC (50-200W) | <1W |
| Cost | PC ($500+) + adapter ($15) | ESP32 ($8) |
| Setup | Command-line args | Web UI / buttons |
| Debugging | Python REPL | Serial monitor |

**Overall:** Standalone keyer is simpler, cheaper, and more portable.

## Troubleshooting

### No Network Connection

- Check Ethernet cable (link LED on module)
- Verify receiver IP address in config
- Try WiFi fallback mode (hold config button)
- Check firewall on receiver (allow port 7356)

### No Audio on Receiver

- Verify receiver running: `ps aux | grep cw_receiver`
- Check receiver listening on correct port: `netstat -ln | grep 7356`
- Increase jitter buffer: `--jitter-buffer 200`
- Check ESP32 serial output for "Connected!"

### Timing Issues

- Check WPM setting matches expectation
- Verify dit duration: `dit_ms = 1200 / wpm`
- Monitor jitter buffer statistics on receiver
- Reduce network latency (use wired Ethernet)

### Garbled CW / State Errors

- Check paddle wiring (no floating inputs)
- Verify pull-ups enabled (pinMode INPUT_PULLUP)
- Add debouncing delay (5ms typical)
- Check for electrical noise (ground loops)

## Future Enhancements

### Planned Features

- [ ] Multiple receiver support (multicast)
- [ ] CW memory recording (store QSO sequences)
- [ ] Prosigns (SK, AR, BT, etc.)
- [ ] Farnsworth timing (character vs word spacing)
- [ ] Weight adjustment (dit/dah ratio tuning)
- [ ] Auto-tune to operator speed
- [ ] OLED display (WPM, mode, status)
- [ ] Rotary encoder (speed/mode adjustment)
- [ ] Battery operation (LiPo + boost converter)

### Advanced Options

- [ ] UDP protocol support (lower latency on LAN)
- [ ] WebSocket mode (browser-based receiver)
- [ ] Morse decoder (bidirectional operation)
- [ ] Contest logging integration
- [ ] WSJT-X/FLdigi compatibility
- [ ] Satellite/packet radio modes

## References

### This Codebase

- **Protocol specification:** `Doc/TCP_TS_PROTOCOL_SPECIFICATION.md`
- **Python reference sender:** `test_implementation/cw_usb_key_sender_tcp_ts.py`
- **Python protocol encoding:** `test_implementation/cw_protocol_tcp_ts.py`
- **Iambic keyer logic:** `test_implementation/iambic_keyer_new.py`
- **TCP-TS receiver:** `test_implementation/cw_receiver_tcp_ts.py`
- **Protocol instructions:** `.github/copilot-instructions.md`

### External Resources

- **ESP32 Arduino Core:** https://github.com/espressif/arduino-esp32
- **WT32-ETH01 Guide:** https://github.com/ldijkman/WT32-ETH01-LAN-8720-RJ45
- **Vail Adapter (reference):** https://github.com/Vail-CW/vail-adapter
- **K3NG Keyer (Arduino):** https://github.com/k3ng/k3ng_cw_keyer

## License

Same as parent project (see root LICENSE file).

## Author

Part of the Duration-Encoded CW Protocol project.

**Hardware platform:** ESP32-WT32-ETH01  
**Firmware:** Arduino C++ / MicroPython  
**Protocol:** TCP-TS (TCP with timestamps)  
**Compatibility:** Existing DECW receivers (Python/Web)
