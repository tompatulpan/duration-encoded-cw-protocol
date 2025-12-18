# USB HID CW Keyer Solutions

**Status:** 🚧 In development - Features and structure subject to change

Hardware solution for connecting CW paddles to the Duration-Encoded CW Protocol over networks and web platform.

## XIAO SAMD21 USB HID Keyer ⭐ **RECOMMENDED**

A compact USB HID device that appears as a keyboard to the host PC. The microcontroller reads paddle inputs and presents them as USB keyboard key presses, which Python software reads and transmits over TCP-TS.

## Quick Start

1. **Flash firmware** to XIAO SAMD21 (see HARDWARE.md)
2. **Connect paddles** to D1 (dah) and D2 (dit), common to GND
3. **Install dependencies:** `pip3 install pyaudio numpy websockets`
4. **Run sender:**
   - LAN: `python3 cw_xiao_sender_tcp_ts.py <receiver_ip>`
   - Web: `python3 cw_xiao_sender_web.py --url <websocket_url> --callsign <your_call>`
5. **Start keying!**

### Why XIAO SAMD21?
- **Proven working design** - See [Vail-CW adapter](https://github.com/Vail-CW/vail-adapter)
- **Built-in USB** - No USB-serial adapter needed
- **Standard HID keyboard** - Works with Arduino Keyboard library
- **Tiny form factor** - 18mm × 21mm
- **Low cost** - ~$5-8 from Seeed or other...

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



### Pin Wiring

```
XIAO SAMD21 Pinout:

   ┌─────────────────────┐
   │  Seeed XIAO SAMD21  │
   │                     │
   │  D2 (PA08) ─────────── Dit paddle input (internal pull-up)
   │  D1 (PA04) ─────────── Dah paddle input (internal pull-up)
   │  GND ───────────────── Common ground to paddles
   │  5V ────────────────── 
   │  USB-C ─────────────── Connect to host PC
   └─────────────────────┘

Paddle Wiring:
  Dit paddle: Normally-open switch between D2 and GND
  Dah paddle: Normally-open switch between D1 and GND
  Common GND: All paddles share common ground
  
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
5. Click Upload (firmware ~35KB, 14% of flash)
6. Verify on Linux: `lsusb -v -d 2886:802f | grep bInterfaceClass` shows "3 HID"

**Debugging Linux:**
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
| **Internet/remote** | `cw_xiao_sender_tcp_ts.py` | Lower latency, direct TCP connection |
| **Multi-user practice** | `cw_xiao_sender_web.py` | Room-based sharing via web platform |
| **Local practice** | `cw_xiao_sender_tcp_ts.py` | Simpler, no internet required |
| **Demo/public display** | `cw_xiao_sender_web.py` | Share link, anyone can watch/decode |

### Troubleshooting

**Device not found:**
```bash
# Check XIAO is connected (should show 2886:802f)
lsusb | grep 2886

# List all hidraw devices
ls -l /dev/hidraw*

# Find which hidraw is the XIAO
for dev in /dev/hidraw*; do
  udevadm info $dev | grep -E 'ID_VENDOR_ID|ID_MODEL_ID'
done
# Look for ID_VENDOR_ID=2886 and ID_MODEL_ID=802f
```

**Permission denied / Cannot open device:**
```bash
# Check current permissions
ls -l /dev/hidraw* | grep -E '(2886|hidraw)'

# Apply udev rule (permanent fix - recommended)
sudo tee /etc/udev/rules.d/99-xiao.rules << EOF
KERNEL=="hidraw*", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="802f", MODE="0666", TAG+="uaccess"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Replug the XIAO USB cable, then test
python3 cw_xiao_sender_tcp_ts.py localhost --debug

# Alternative: Temporarily use sudo (not recommended)
sudo python3 cw_xiao_sender_tcp_ts.py localhost
```


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

- 



---

## ESP32 Standalone Keyer (Future)

An ESP32-based standalone keyer is planned for future development. It would eliminate the need for a PC by implementing the keyer and network protocol directly in firmware.

**Status:** Design only, not yet implemented. XIAO solution (above) is currently recommended.

See `esp32_cw_keyer.ino` for firmware skeleton and design notes.

