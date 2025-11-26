# Remote CW - Real-Time Morse Code over UDP
**Status:** 🚧 In development!  
This project is not production-ready. Features, structure, and documentation are subject to rapid change.

A lightweight, real-time protocol for transmitting Morse code timing over IP networks with sub-second latency. Inspired by DL4YHF's CW protocol with modern adaptive jitter buffering.

**Design Goal:** Simple setup in Linux (or Windows) using Python's cross-platform capabilities - no complex dependencies or compilation required. Just install Python packages and run.

**Note:** Currently supports audio sidetone output. Physical key-jack output (for driving remote transmitters) is not yet implemented.

## Installation

### Linux (Fedora, Ubuntu, Debian)

**Install Python and audio dependencies:**
```bash
# Fedora
sudo dnf install python3 python3-pip python3-pyaudio portaudio

# Ubuntu/Debian
sudo apt install python3 python3-pip python3-pyaudio portaudio19-dev
```

**Install Python packages:**
```bash
pip3 install pyserial pyaudio numpy
```

**Serial port permissions (for USB keys):**
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Or create udev rule for immediate access
echo 'KERNEL=="ttyUSB[0-9]*", MODE="0666"' | sudo tee /etc/udev/rules.d/50-ttyusb.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# Logout/login or reboot for group membership to take effect
```

### Windows (Not tested yet)

**Install Python:**
1. Download Python 3.14+ from [python.org](https://www.python.org/downloads/)
2. During installation, check "Add Python to PATH"

**Install Python packages:**
```cmd
pip install pyserial pyaudio numpy
```

**Audio troubleshooting:**
- If PyAudio install fails, download precompiled wheel from [PyAudio Windows wheels](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)
- Install with: `pip install PyAudio‑0.2.14‑cp314‑cp314‑win_amd64.whl`

**USB serial drivers:**
- Most USB-to-serial adapters work automatically
- Check Device Manager for COM port number (e.g., COM3)
- Use this port in commands: `python cw_usb_key_sender.py localhost iambic-b 25 COM3`

## Quick Start

**Send automated CW:**
```bash
python3 cw_auto_sender.py localhost "CQ CQ CQ DE SM0XXX" 20
```

**Interactive sending:**
```bash
python3 cw_interactive_sender.py localhost 20
```

**Hardware key/paddles:**
```bash
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0 --sidetone-freq 700
```

**Receive:**
```bash
python3 cw_receiver.py --buffer 100
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

### Pin Assignments (USB Serial Adapter)

**Straight Key:**
- CTS (pin 8) → Key tip
- GND (pin 5) → Key ring

**Iambic Paddles:**
- CTS (pin 8) → Dit paddle
- DSR (pin 6) → Dah paddle
- GND (pin 5) → Common ground

### TX Sidetone Feature

The sender can generate local audio feedback (sidetone) to eliminate the jitter buffer delay when monitoring your own transmission:

- Enabled by default with `--sidetone`
- Disable with `--no-sidetone`
- Adjustable frequency: `--sidetone-freq 700` (default: 600Hz)
- Zero latency - hear your keying instantly
- Independent from receiver sidetone

Recommended: Use TX sidetone for immediate feedback, disable RX sidetone (`--no-sidetone` on receiver) to avoid doubled audio.

## Technical Specification

### Protocol Format

**Packet Structure (3 bytes):**
```
Byte 0: Sequence number (0-255, wraps)
Byte 1: Flags
  Bit 7:    Key state (1=DOWN, 0=UP)
  Bits 6-0: Duration high bits (MSB of 7-bit value)
Byte 2: Duration low bits (LSB of 7-bit value)
```

**Duration Encoding:**
- 7-bit value (0-127)
- Each unit = 3ms
- Total range: 0-381ms
- Resolution: 3ms steps

**Transport:**
- UDP port 7355
- No acknowledgments (fire-and-forget)
- Sequence numbers for packet loss detection

### Timing Standard

**PARIS Standard:**
- Dit duration = 1200ms / WPM
- Dah duration = 3 × dit
- Element spacing = 1 dit (between dits/dahs in a character)
- Character spacing = 3 dits (between characters)
- Word spacing = 7 dits (between words)

**Example at 20 WPM:**
- Dit: 60ms
- Dah: 180ms
- Element space: 60ms
- Character space: 180ms
- Word space: 420ms

### Jitter Buffer Algorithm

**Relative Timing Model:**
- First packet: Schedule playout at `now + buffer_ms`
- Subsequent packets: Schedule at previous event end time
- Trust packet durations (preserve sender timing exactly)

**Adaptive Shifting:**
- If playout time < arrival time: Shift timeline forward
- Tracks shifts after >100ms gaps (manual keying pauses)
- Statistics differentiate network jitter from operator pauses

**Buffer Recommendations:**
- Localhost: 20-50ms
- LAN: 50-100ms
- Internet: 100-200ms
- Default: 100ms

### State Validation

**DOWN/UP Alternation:**
- Every DOWN event must be followed by UP
- Every UP event must be followed by DOWN
- Violations logged as state errors (non-fatal)
- Useful for debugging protocol issues

### Iambic Keyer Logic

**State Machine:**
- Three states: IDLE, DIT, DAH
- Mode A: Basic alternation
- Mode B: Paddle memory (squeeze mode)

**Paddle Memory (Mode B):**
- Sample opposite paddle during element generation
- If pressed: Set memory flag
- On element completion: Check memory, alternate if set
- Allows smooth dah-dit-dah-dit sequences from "squeezing"

**Character Spacing:**
- Hardware senders: Local sleep after last element
- Reason: Don't know which element is last until paddles released
- All elements send UP with element_space duration
- After returning to IDLE: Sleep for (char_space - element_space)

### Audio Generation

**Sidetone Synthesis:**
- Pure sine wave at configurable frequency (600-800Hz typical)
- Sample rate: 48kHz
- Format: 32-bit float
- Envelope shaping: 5ms rise/fall (reduces clicks)
- Amplitude: 0.3 (30% of full scale)

**TX Sidetone (Zero Latency):**
- Generated in sender process
- Audio callback synchronized with key_down state
- No network dependency
- PyAudio stream with 512-sample buffer

**RX Sidetone (Buffered):**
- Generated in receiver process
- Synchronized with jitter buffer playout
- Includes network latency + buffer delay
- Smooth playback with jitter compensation

### Performance Characteristics

**Latency:**
- TX sidetone: < 1ms (local audio callback)
- RX on localhost: 50-100ms (buffer + audio)
- RX on Internet: 150-250ms (network + buffer + audio)

**Bandwidth:**
- 3 bytes per event
- Typical 20 WPM sending: ~50 bytes/second
- Network impact: Negligible

**Packet Loss Handling:**
- Graceful degradation (missing dits/dahs)
- Sequence numbers detect loss
- No retransmission (real-time priority)
- Manual correction by operator

### Dependencies

- Python 3.14+
- pyserial (for USB key sender)
- pyaudio (for sidetone generation)
- numpy (for audio synthesis)

### Protocol Comparison

**vs. DL4YHF Original:**
- Similar: Packet format, duration encoding, UDP transport
- Enhanced: Adaptive jitter buffer, state validation, statistics
- Added: TX sidetone, iambic keyer, multiple sender modes

**vs. Traditional CW:**
- Preserves exact timing (not just text)
- Sub-second latency over Internet
- Works with physical keys/paddles
- Natural feel for experienced operators

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

**Tested on:**
- Linux (Fedora, Ubuntu, Debian)
- Windows (with Python 3.14+)

**Requirements:**
- Python 3.14 or later
- `pip install pyserial pyaudio numpy`
- USB serial adapter (for hardware keys)

**Cross-Platform Notes:**
- Serial ports: `/dev/ttyUSB0` (Linux) or `COM3` (Windows)
- Audio works on both platforms via PyAudio
- All scripts run unchanged across platforms

## Examples

**Localhost testing with low latency:**
```bash
# Terminal 1
python3 cw_receiver.py --buffer 20 --no-sidetone

# Terminal 2  
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0 --sidetone-freq 700
```

**Internet operation:**
```bash
# Remote receiver
python3 cw_receiver.py --buffer 150

# Local sender with TX monitoring
python3 cw_usb_key_sender.py remote.example.com iambic-b 20 /dev/ttyUSB0
```

**Automated beacon:**
```bash
while true; do
  python3 cw_auto_sender.py remote.example.com "CQ CQ DE SM0XXX" 20
  sleep 60
done
```

## Future Enhancements

**Planned features:**
- [ ] Physical key-jack output (drive remote transmitter via serial DTR/RTS)
- [ ] CW decoder (timing-to-text)
- [ ] Multi-user relay server
- [ ] Web-based interface
- [ ] Recording and playback

## License

Public domain / MIT - Use as you wish.

## Credits

- Protocol concept: Thomas Sailer (DL4YHF)
- Iambic keyer reference: Steve Haynal (n1gp/iambic-keyer)
- Implementation: 2025

## 73!

Happy CW operating!
73 de SM0ONR
