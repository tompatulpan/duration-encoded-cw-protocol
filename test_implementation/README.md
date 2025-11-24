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

- `cw_sender.py` - Terminal-based CW sender (Space = key down)
- `cw_receiver.py` - Terminal-based CW receiver with audio output
- `cw_protocol.py` - Shared protocol implementation
- `test_loopback.sh` - Automated test script

## Usage

### Terminal 1 (Receiver):
```bash
python3 cw_receiver.py
```

### Terminal 2 (Sender):
```bash
python3 cw_sender.py localhost
```

Press and hold **SPACE** to key down, release to key up.
Press **Q** to quit.

## Testing

Run automated loopback test:
```bash
./test_loopback.sh
```

This will measure:
- Round-trip latency
- Timing accuracy
- Packet loss handling
