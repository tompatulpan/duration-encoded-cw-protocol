# CW Protocol Test Implementation

This is a minimal test implementation of the DL4YHF-inspired CW keying protocol over UDP for local Linux testing.

## Key Differences from Original DL4YHF Protocol

### Original DL4YHF (Remote CW Keyer):
1. **Transport**: Uses TCP with multiplexed bytestreams
2. **Timing Encoding**: Non-linear compression (0-1165ms range)
   ```
   0x00-0x1F: Direct 0-31ms (1ms resolution)
   0x20-0x3F: 32 + 4*(value-0x20) ms (4ms resolution)  
   0x40-0x7F: 157 + 16*(value-0x40) ms (16ms resolution, max 1165ms)
   ```
3. **Protocol**: Custom binary multiplexing for CW + audio + control over single TCP socket
4. **Context**: Windows-based, integrated with serial ports and audio

### Our Test Implementation:
1. **Transport**: Pure UDP for minimal latency testing
2. **Timing Encoding**: Optimized for typical CW speeds (0-384ms range)
   ```
   0x00-0x3F: Direct 0-63ms (1ms resolution) - covers 15-60 WPM
   0x40-0x5F: 64 + 2*(value-64) ms (2ms resolution, 64-126ms)
   0x60-0x7F: 128 + 8*(value-96) ms (8ms resolution, 128-384ms)
   ```
3. **Protocol**: Simplified with 3-byte header + payload
4. **Context**: Cross-platform, terminal-based testing

### Why the Changes?

**Better resolution for common speeds**: 
- Most CW operation is 15-30 WPM (40-80ms dit length)
- Our 0-63ms direct encoding covers this perfectly with 1ms resolution
- DL4YHF's direct encoding only goes to 31ms (good for >38 WPM)

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
- `cw_receiver.py` - Terminal-based receiver with **jitter buffer** support

### Senders
- `cw_sender.py` - Terminal-based sender (Space = key down)
- `cw_auto_sender.py` - Automated sender (text to CW conversion)
- `cw_interactive_sender.py` - Interactive sender (type-ahead with queue)
- `cw_usb_key_sender.py` - USB serial key interface with iambic keyer

### Testing Tools
- `test_loopback.sh` - Automated test script
- `test_udp_connection.py` - UDP connectivity diagnostics
- `test_jitter_buffer.py` - Jitter buffer validation test

### Documentation
- `JITTER_BUFFER.md` - Complete jitter buffer guide
- `requirements.txt` - Python dependencies

## Usage

### Local/LAN Testing

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
