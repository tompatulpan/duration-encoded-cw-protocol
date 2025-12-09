# CW Protocol Test Implementation

This is a test implementation of the Duration-Encoded CW (DECW) protocol over UDP.

## Key Differences from Original DL4YHF Protocol

### Original DL4YHF (Remote CW Keyer):
1. **Transport**: Uses TCP
2. **Timing Encoding**: Non-linear compression (0-1165ms range)
   ```
   0x00-0x1F: Direct 0-31ms (1ms resolution)
   0x20-0x3F: 32 + 4*(value-0x20) ms (4ms resolution)  
   0x40-0x7F: 157 + 16*(value-0x40) ms (16ms resolution, max 1165ms)
   ```
3. **Packet Format**: 1 byte per event (state in bit 7, duration in bits 0-6)
4. **Context**: Part of complete remote station system (Windows-based)

### Our Implementation (DECW):
1. **Transport**: Uses UDP
2. **Timing Encoding**: Direct encoding optimized for common CW speeds
   ```
   0-255ms direct (1ms resolution)
   ```
3. **Packet Format**: 3 bytes per event (sequence, state, duration as separate fields)
4. **Context**: Standalone CW protocol (cross-platform, terminal-based)

### Why the Changes?

**Better resolution for common speeds**: 
- Most CW operation is 15-30 WPM (40-80ms dit length)
- Our 0-63ms direct encoding covers this perfectly with 1ms resolution
- DL4YHF uses variable resolution: 1ms (0-31ms), 4ms (32-126ms), 16ms (128-1165ms)
- Both approaches work well, but DECW's simpler encoding is easier to implement

**Simpler UDP packets**:
- Each UDP packet is independent (no TCP stream multiplexing)
- Easier to test and debug
- Lower latency (no TCP overhead)

**Sequence numbers in header**:
- Track packet ordering
- Detect loss
- Enable out-of-order delivery handling

## Files

### Core Protocol
- `cw_protocol.py` - Shared protocol implementation with timing encoding/decoding

### Receivers
- `cw_receiver.py` - Terminal-based receiver with jitter buffer support
- `cw_receiver_fec.py` - **FEC-enabled receiver (handles packet loss)**
- `cw_gpio_output.py` - Raspberry Pi GPIO output for physical key control

### Senders
- `cw_auto_sender.py` - Automated sender (text to CW conversion)
- `cw_interactive_sender.py` - Interactive sender (type-ahead with queue)
- `cw_sender_fec_sim.py` - **FEC sender with network simulation (testing)**
- `cw_usb_key_sender.py` - USB serial key interface with iambic keyer

### Protocol Implementation
- `cw_protocol_fec.py` - **Reed-Solomon FEC implementation**

### Testing Tools
- `test_loopback.sh` - Automated test script
- `test_udp_connection.py` - UDP connectivity diagnostics
- `test_jitter_buffer.py` - Jitter buffer validation test
- `test_keyer_output.py` - Keyer logic validation
- `fec_calculator.py` - **FEC performance calculator**

## Dependencies

### System Requirements
```bash
# For audio support (sidetone)
sudo apt-get install python3-pyaudio portaudio19-dev

# For FEC support (packet loss recovery)
pip install reedsolo

# Or install in virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install reedsolo pyaudio numpy
```

### Optional Dependencies
- **PyAudio** - Audio sidetone generation (receiver audio feedback)
- **reedsolo** - Reed-Solomon FEC for packet loss recovery
- **numpy** - Audio signal processing (required with PyAudio)

Without these, the system runs in "visual only" mode (no audio, no FEC).

## Usage

### Local/LAN Testing (No Packet Loss)

**Terminal 1 (Receiver):**
```bash
python3 cw_receiver.py
```

**Terminal 2 (Sender):**
```bash
python3 cw_sender.py localhost
```

Press and hold **SPACE** to key down, release to key up.
Press **Q** to quit.

### Internet/WAN Usage

**Receiver (enable jitter buffer for smooth timing):**
```bash
# Recommended for internet use
python3 cw_receiver.py --jitter-buffer 100
```

**Sender (from remote location):**
```bash
python3 cw_interactive_sender.py <receiver_public_ip> 7355
```

**Note:** Receiver must configure router port forwarding (UDP 7355)

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

**With straight key:**
```bash
python3 cw_usb_key_sender.py localhost
```

**With iambic paddles (Mode B recommended):**
```bash
python3 cw_usb_key_sender.py localhost --mode iambic-b --wpm 25
```

Modes: `straight`, `bug`, `iambic-a`, `iambic-b`

## Testing

### Basic Loopback Test
```bash
./test_loopback.sh
```
Measures: latency, timing accuracy, packet loss

### UDP Connection Test
```bash
python3 test_udp_connection.py <remote_ip> 7355
```
Validates: connectivity, firewall, NAT traversal

### Jitter Buffer Test
```bash
# Terminal 1: Receiver without buffer
python3 cw_receiver.py

# Terminal 2: Send with simulated jitter
python3 test_jitter_buffer.py --jitter 50
# Result: You'll hear uneven timing

# Terminal 1: Receiver WITH buffer
python3 cw_receiver.py --jitter-buffer 100

# Terminal 2: Send with simulated jitter
python3 test_jitter_buffer.py --jitter 50
# Result: Smooth, consistent timing
```

See `JITTER_BUFFER.md` for complete guide.

## Jitter Buffer (NEW)

For **internet/WAN use**, enable the jitter buffer to smooth out network timing variations:

```bash
python3 cw_receiver.py --jitter-buffer 100
```

**Why use it?**
- Compensates for variable network delays
- Smooths "stuttering" sidetone
- Makes internet CW sound like local CW

**Buffer size recommendations:**
- `50ms` - Fast internet, low jitter
- `100ms` - **Standard internet (recommended)**
- `150-200ms` - Poor connection, high jitter
- `0ms` - Disabled (LAN mode, default)

**Trade-off:** Higher buffer = smoother timing, but adds latency to QSO

See `JITTER_BUFFER.md` for detailed configuration guide.

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

## Forward Error Correction (FEC)

**NEW:** Reed-Solomon FEC for reliable CW over lossy networks (WiFi, cellular, internet).

### Why FEC?

Traditional UDP has no packet loss recovery. On poor networks (WiFi with interference, cellular, satellite):
- Lost packets = missing CW elements
- Distorted timing
- Garbled characters

**FEC solves this** by sending redundant data that can reconstruct lost packets.

### FEC Performance

| Network Loss | FEC Recovery | Result          |
|--------------|--------------|-----------------|
| 5%           | >95%         | ✓✓✓ Excellent   |
| 10%          | >90%         | ✓✓ Optimal      |
| 15%          | >80%         | ✓ Good          |
| 20%          | ~65%         | ⚠ Marginal      |
| 25%+         | <50%         | ✗ Poor          |

**Sweet spot:** 5-15% packet loss → Near-perfect recovery

### Using FEC

**Receiver (with FEC):**
```bash
# Requires: pip install reedsolo
python3 cw_receiver_fec.py --jitter-buffer 200
```

**Note:** FEC requires 200ms+ jitter buffer (FEC packets arrive after data packets)

**Sender (with FEC):**
```bash
# Production use (no simulation)
python3 cw_sender_fec.py <remote_ip> 25 "CQ CQ DE CALLSIGN"

# Testing with network simulation
python3 cw_sender_fec_sim.py <remote_ip> 25 "test" --loss 0.10 --jitter 30
```

**Loss parameter:** Decimal fraction (0.0 to 1.0)
- `--loss 0.05` = 5% packet loss
- `--loss 0.10` = 10% packet loss
- `--loss 0.20` = 20% packet loss

### FEC Testing Examples

**1. Perfect network (0% loss):**
```bash
# Terminal 1
python3 cw_receiver_fec.py --jitter-buffer 200

# Terminal 2
python3 cw_sender_fec_sim.py localhost 25 "test" --loss 0.0 --jitter 0
# Result: Perfect reception
```

**2. Good WiFi (5% loss):**
```bash
python3 cw_sender_fec_sim.py localhost 25 "cq cq de test" --loss 0.05 --jitter 20
# Result: >95% recovery, nearly perfect
```

**3. Poor WiFi (15% loss):**
```bash
python3 cw_sender_fec_sim.py localhost 25 "cq cq de test" --loss 0.15 --jitter 50
# Result: >80% recovery, some gaps
```

**4. Extreme conditions (25% loss):**
```bash
python3 cw_sender_fec_sim.py localhost 25 "cq cq de test" --loss 0.25 --jitter 80
# Result: ~50% recovery, many gaps
```

### FEC Calculator

Calculate optimal settings for your network:

```bash
# Interactive mode
python3 fec_calculator.py

# Direct calculation
python3 fec_calculator.py 10% 30
# Input: 10% loss, ±30ms jitter
# Output: Recommended 200ms buffer, 90% recovery rate
```

### FEC Documentation

- `FEC_PERFORMANCE_GUIDE.md` - Comprehensive performance analysis
- `FEC_QUICK_REFERENCE.txt` - Quick reference card with tables
- `fec_calculator.py` - Interactive calculator

### FEC Technical Details

**Algorithm:** Reed-Solomon error correction
- **Block size:** 10 data packets
- **Redundancy:** 6 FEC packets (18 parity bytes)
- **Recovery limit:** Up to 3 lost packets per block (30% within block)
- **Overhead:** 60% additional bandwidth

**Constraint:** Requires ALL 6 FEC packets to attempt recovery. If FEC packets are also lost, recovery may fail.

**Best for:** Networks with 5-15% random packet loss
