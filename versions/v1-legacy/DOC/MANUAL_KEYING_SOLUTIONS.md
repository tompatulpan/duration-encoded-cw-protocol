# Handling Manual Keying Timing and Spacing - Practical Solutions

## Problem Statement

When transmitting Morse code from a manual key (straight key, paddle, etc.), the operator's timing is **intentionally imperfect**. This creates challenges:

1. **Variable spacing:** Character and word spaces vary from transmission to transmission
2. **The "fist":** Each operator has unique timing characteristics that must be preserved
3. **Network vs operator delays:** How to distinguish network jitter from intentional pauses?

## Quick Answer

**Use duration encoding with relative timing (already implemented in UDP version):**
- ✅ Encode duration in each packet (not derived from arrival time)
- ✅ Schedule events relative to previous event end time
- ✅ This makes timing **immune to network jitter**
- ✅ Works the same for TCP and UDP (application-layer solution)

---

## Solution Overview

### Current Implementation (UDP Protocol)

The existing implementation at `/home/tomas/Documents/Projekt/CW/protocol/test_implementation/` **already solves this problem correctly**:

#### 1. Duration Encoding (Sender Side)

```python
# cw_usb_key_sender.py
def on_key_event(self, key_down):
    current_time = time.time()
    duration_ms = (current_time - self.last_event_time) * 1000
    
    # Duration is calculated at sender - not affected by network!
    packet = self.protocol.create_packet(key_down, duration_ms)
    self.sock.sendto(packet, (self.host, self.port))
    
    self.last_event_time = current_time
```

**Key insight:** Duration represents the **actual time on the operator's side**, not the network delay.

#### 2. Relative Timing (Receiver Side)

```python
# cw_receiver.py - JitterBuffer class
def add_event(self, key_down, duration_ms, arrival_time):
    # Schedule based on when PREVIOUS event ends (relative timing)
    if self.last_event_end_time is None:
        # First event - add buffer delay
        playout_time = time.time() + self.buffer_ms / 1000.0
    else:
        # Subsequent events - schedule relative to last event end
        playout_time = self.last_event_end_time
    
    # Schedule event
    self.event_queue.put((playout_time, key_down, duration_ms))
    
    # Track when THIS event will end (for next event)
    self.last_event_end_time = playout_time + duration_ms / 1000.0
```

**Result:** Network jitter doesn't affect playback timing because:
- Duration comes from packet (operator side measurement)
- Events play relative to each other (not based on arrival times)
- Operator's timing is perfectly preserved

---

## Why This Works

### Example: Manual Keying with Network Jitter

**Operator sends (actual timing):**
```
Event 1: KEY DOWN, duration=55ms   (send at t=0ms)
Event 2: KEY UP,   duration=65ms   (send at t=55ms)
Event 3: KEY DOWN, duration=180ms  (send at t=120ms)
```

**Network adds jitter:**
```
Packet 1 arrives: t=0ms   + 10ms jitter  = t=10ms
Packet 2 arrives: t=55ms  + 50ms jitter  = t=105ms (late!)
Packet 3 arrives: t=120ms + 5ms jitter   = t=125ms
```

**Receiver playback (relative timing):**
```
Event 1: Play at t=110ms (10ms arrival + 100ms buffer)
         Play for 55ms (from packet)
         End at t=165ms

Event 2: Play at t=165ms (when Event 1 ends - IGNORE arrival time!)
         Play for 65ms (from packet)
         End at t=230ms

Event 3: Play at t=230ms (when Event 2 ends)
         Play for 180ms (from packet)
         End at t=410ms
```

**Result:** Perfect timing reconstruction despite network jitter! 🎉

### Comparison: Absolute Timing (Wrong Approach)

If you based timing on arrival times (DON'T DO THIS):

```python
# WRONG - Don't do this!
playout_time = arrival_time + buffer_delay
```

Then with the jitter example above:
```
Event 1: Play at t=110ms, duration 55ms → end at t=165ms ✓
Event 2: Play at t=205ms, duration 65ms → end at t=270ms ✗ (should be 165ms!)
         Gap of 40ms introduced by network jitter!
Event 3: Play at t=225ms, duration 180ms → OVERLAPS Event 2! ✗✗
```

**Absolute timing breaks with network jitter!**

---

## Handling Different Spacing Types

### The Challenge

Manual keying has three types of spaces:
1. **Element space:** Between dit/dah within a character (~1× dit length)
2. **Character space:** Between characters (~3× dit length)  
3. **Word space:** Between words (~7× dit length)

But human timing is variable:
```
Element space:    40-80ms   (should be ~60ms at 20 WPM)
Character space:  150-250ms (should be ~180ms)
Word space:       300-600ms (should be ~420ms)
```

### Solution: Adaptive Spacing Detection

The protocol handles this at the **decoder level** (optional component):

```python
# cw_usb_key_sender_with_decoder.py - SimpleCWDecoder class
class SimpleCWDecoder:
    def __init__(self, wpm=20):
        self.wpm = wpm
        self.update_timing()
        self.element_buffer = []
        
    def update_timing(self):
        """Calculate timing thresholds based on current WPM estimate"""
        dit_duration = 1200 / self.wpm
        
        # Adaptive thresholds with tolerance
        self.dit_threshold = dit_duration * 1.5
        self.char_space_threshold = dit_duration * 2.0
        self.word_space_threshold = dit_duration * 5.0
    
    def add_element(self, key_down, duration_ms):
        """Process key event and classify spacing"""
        if key_down:
            # Dit or dah
            if duration_ms < self.dit_threshold:
                self.element_buffer.append('.')
            else:
                self.element_buffer.append('-')
        else:
            # Space - classify type
            if duration_ms > self.word_space_threshold:
                return self.decode_character(), 'word'
            elif duration_ms > self.char_space_threshold:
                return self.decode_character(), 'char'
            else:
                return None, 'element'  # Inter-element space
    
    def decode_character(self):
        """Convert element buffer to character"""
        pattern = ''.join(self.element_buffer)
        self.element_buffer = []
        return MORSE_CODE.get(pattern, '?')
```

**Key features:**
- Thresholds adapt to detected WPM
- Tolerant to timing variations (1.5×, 2×, 5× multipliers)
- Can be updated in real-time as operator speed changes

### Adaptive WPM Estimation

To handle speed changes during transmission:

```python
class AdaptiveWPMEstimator:
    def __init__(self):
        self.dit_history = []
        self.window_size = 10
    
    def add_element(self, duration_ms, is_dit):
        """Track recent dit durations"""
        if is_dit:
            self.dit_history.append(duration_ms)
            if len(self.dit_history) > self.window_size:
                self.dit_history.pop(0)
    
    def get_wpm(self):
        """Estimate current WPM from recent dits"""
        if len(self.dit_history) < 3:
            return 20  # Default
        
        # Use median (robust to outliers)
        sorted_dits = sorted(self.dit_history)
        median_dit = sorted_dits[len(sorted_dits) // 2]
        
        # WPM = 1200 / dit_duration_ms
        wpm = 1200 / median_dit
        return max(5, min(wpm, 60))  # Clamp to reasonable range
```

**Usage:**
```python
estimator = AdaptiveWPMEstimator()
decoder = SimpleCWDecoder(wpm=20)

def on_element(key_down, duration_ms):
    # Update WPM estimate
    if key_down and duration_ms < 100:  # Likely a dit
        estimator.add_element(duration_ms, is_dit=True)
        current_wpm = estimator.get_wpm()
        decoder.wpm = current_wpm
        decoder.update_timing()
    
    # Decode element
    result = decoder.add_element(key_down, duration_ms)
    if result:
        char, space_type = result
        print(char, end=' ' if space_type == 'word' else '')
```

---

## TCP vs UDP: Does It Matter?

### Short Answer: No (for manual keying)

The duration encoding + relative timing solution works **identically** for TCP and UDP because it's an **application-layer solution**.

Both protocols:
1. Deliver packets containing `(key_down, duration_ms)`
2. Receiver uses relative timing algorithm
3. Network timing doesn't affect playback

### Differences Are Network-Layer

The TCP vs UDP choice affects:
- **Packet loss handling** (gaps vs delays)
- **Latency predictability** (consistent vs variable)
- **Jitter buffer effectiveness** (controlled vs uncontrolled)

But **not** the manual keying timing preservation!

### Recommendation

Use **UDP with jitter buffer** because:
- More predictable latency
- Better packet loss behavior (gaps vs delays)
- Explicit control over buffering

But if you must use TCP (firewall reasons), the manual keying solution still works fine.

---

## Practical Configuration Examples

### Local Network (Minimal Jitter)

```bash
# Receiver - small buffer
python3 cw_receiver.py --jitter-buffer 20

# Sender - USB key with decoder
python3 cw_usb_key_sender_with_decoder.py --port /dev/ttyUSB0 --wpm 20
```

**Settings:**
- Buffer: 20ms (LAN has minimal jitter)
- WPM: 20 (decoder starting point, adapts automatically)

### Internet Connection (Variable Jitter)

```bash
# Receiver - larger buffer
python3 cw_receiver.py --jitter-buffer 150

# Sender - USB key with FEC
python3 cw_usb_key_sender_with_decoder_fec.py --host operator.example.com --port /dev/ttyUSB0
```

**Settings:**
- Buffer: 150ms (absorbs internet jitter)
- FEC: Enabled (handles packet loss)

### Contest/DX Operation (Quality Priority)

```bash
# Receiver - balanced settings
python3 cw_receiver_fec.py --jitter-buffer 150 --frequency 550

# Sender - straight key with adaptive spacing
python3 cw_usb_key_sender.py --mode straight --wpm 25
```

**Settings:**
- Buffer: 150ms (good quality)
- FEC: Enabled (reliability)
- Frequency: 550Hz (comfortable tone)
- Mode: Straight key (most natural)

---

## Testing Your Setup

### Test 1: Verify Timing Preservation

Send a known pattern and compare timing:

```bash
# Terminal 1: Receiver with logging
python3 cw_receiver.py --jitter-buffer 100 --debug

# Terminal 2: Send test pattern
python3 cw_auto_sender.py --message "PARIS" --wpm 20

# Expected output: 
# DIT:  60ms ± 5ms
# DAH:  180ms ± 5ms
# Spaces preserved within ±10ms
```

### Test 2: Manual Keying Under Jitter

Simulate network jitter and test manual input:

```bash
# Terminal 1: Add network jitter (requires root)
sudo tc qdisc add dev lo root netem delay 50ms 20ms

# Terminal 2: Receiver
python3 cw_receiver.py --jitter-buffer 100

# Terminal 3: Manual sender
python3 cw_usb_key_sender.py --port /dev/ttyUSB0

# Test: Send irregular timing (vary your spacing)
# Expected: Timing preserved despite network jitter
```

### Test 3: Spacing Detection

Test adaptive spacing detection:

```bash
# Sender with decoder
python3 cw_usb_key_sender_with_decoder.py --port /dev/ttyUSB0 --wpm 20

# Send: "CQ CQ DE MYCALL"
# Vary your spacing between characters and words
# Expected: Decoder adapts to your timing and correctly identifies spaces
```

---

## Troubleshooting

### Problem: Timing Sounds Distorted

**Symptoms:**
- Elements sound rushed or stretched
- Inconsistent playback speed

**Causes:**
1. Using absolute timing instead of relative
2. Jitter buffer too small
3. Buffer underrun (events arriving too late)

**Solutions:**
```bash
# Increase buffer size
python3 cw_receiver.py --jitter-buffer 200

# Check for packet loss
python3 cw_receiver.py --debug

# Use FEC version if packet loss > 2%
python3 cw_receiver_fec.py --jitter-buffer 150
```

### Problem: Spacing Detection Unreliable

**Symptoms:**
- Characters merge together
- Words split incorrectly
- Decoder shows "?" frequently

**Causes:**
1. WPM estimate wrong
2. Inconsistent operator timing
3. Thresholds too tight

**Solutions:**
```python
# Adjust thresholds in decoder
decoder.dit_threshold = dit_duration * 2.0      # More tolerant (was 1.5)
decoder.char_space_threshold = dit_duration * 2.5  # Lower threshold (was 2.0)
decoder.word_space_threshold = dit_duration * 4.5  # Lower threshold (was 5.0)
```

Or use manual WPM specification:
```bash
python3 cw_usb_key_sender_with_decoder.py --wpm 18  # Force specific WPM
```

### Problem: "Invalid State" Errors (DOWN-DOWN or UP-UP)

**Symptoms:**
```
[ERROR] Invalid state: got DOWN twice in a row
```

**Causes:**
1. Packet loss (UDP)
2. Retransmission delay (TCP)

**Solutions:**
- UDP: Enable FEC
  ```bash
  python3 cw_receiver_fec.py --jitter-buffer 150
  python3 cw_sender_fec.py --host example.com
  ```
  
- TCP: Increase buffer, check network quality
  
- Both: Errors are logged but playback continues (non-fatal)

---

## Summary Recommendations

### For TCP Implementation

If using TCP protocol:

1. **Keep duration encoding** (measure timing on sender side)
2. **Use relative timing** on receiver (schedule events based on previous event end)
3. **Add small jitter buffer** (20-50ms) even with TCP
4. **Disable Nagle's algorithm** (`TCP_NODELAY`)
5. **Use adaptive spacing detection** for decoding

### For UDP Implementation (Current)

Already correctly implemented:

1. ✅ Duration encoding (see `cw_usb_key_sender.py`)
2. ✅ Relative timing (see `cw_receiver.py` - `JitterBuffer` class)
3. ✅ Adaptive buffer sizing (configurable via `--jitter-buffer`)
4. ✅ Spacing detection (see `cw_usb_key_sender_with_decoder.py`)
5. ✅ FEC option for packet loss (see `cw_receiver_fec.py`)

### Key Takeaway

**The manual keying problem is solved by:**
1. Encoding duration in packets (not deriving from network timing)
2. Relative timing on receiver (immune to jitter)
3. Adaptive spacing detection (handles variable operator timing)

These solutions work **the same** for TCP and UDP - the choice of protocol affects latency and loss behavior, not timing preservation.

---

## References

- Duration encoding: `test_implementation/cw_protocol.py`
- Relative timing: `test_implementation/cw_receiver.py` (JitterBuffer class)
- Spacing detection: `test_implementation/cw_usb_key_sender_with_decoder.py` (SimpleCWDecoder)
- Full comparison: `test_implementation/Doc/TCP_UDP_COMPARISON.md`

**Last Updated:** December 10, 2025
