# CW Protocol Timing Diagrams

Visual representation of packet timing, buffering, and EOT behavior.

## Scenario 1: Single Character with TX and RX Sidetone

```
Letter "A" (dit-dah) at 20 WPM
Dit = 60ms, Dah = 180ms, Element space = 60ms

TX Side (Sender):
Time:     0ms   60ms  120ms  300ms  360ms
          |-----|-----|------|------|
Paddle:   [DIT] [UP ] [DAH  ] [UP  ]
TX Audio: [beep]       [beeeep]              ← Instant local sidetone
Packets:  [DN→] [UP→] [DN→ ] [UP→ ]          ← Sent immediately

RX Side (Receiver with 100ms buffer):
Time:     0ms        100ms  160ms  220ms  400ms  460ms
          |----------|------|------|------|------|
Packets:  [DN][UP][DN][UP  ]                     ← Arrive instantly (localhost)
Buffer:              [DIT ] [UP ] [DAH  ] [UP  ] ← Scheduled playout
RX Audio:            [beep]       [beeeep]       ← 100ms delayed

User hears:
  - TX audio at 0ms, 120ms
  - RX audio at 100ms, 220ms
  - 100ms echo between TX and RX
```

**Observation:** 
- TX sidetone = immediate feedback
- RX sidetone = buffered, accurate network timing
- Both play correctly, just offset by buffer delay

---

## Scenario 2: Rapid Dits Without EOT

```
Three separate dits sent with pauses

TX Side:
Time:     0ms   60ms  120ms  500ms  560ms  620ms  1000ms 1060ms 1120ms
          |-----|-----|------|------|------|------|-------|------|------|
Paddle:   [DIT] [UP ]  (gap) [DIT ] [UP  ]  (gap) [DIT  ] [UP  ]
Packets:  [DN→] [UP→]        [DN→ ] [UP→ ]        [DN→  ] [UP→ ]

RX Side (100ms buffer, NO EOT):
Time:     100ms 160ms 220ms  600ms  660ms  720ms  1100ms 1160ms 1220ms
          |-----|-----|------|------|------|------|-------|------|------|
Buffer:   [DIT] [UP ]  (gap) [DIT ] [UP  ]  (gap) [DIT  ] [UP  ]
RX Audio: [beep]              [beep]              [beep  ]

Timeline: ═════════════════════════════════════════════════════════════→
          ^                   ^                   ^
          Initial buffer      Continue timeline   Continue timeline
```

**Observation:**
- Timeline continues smoothly
- Gaps preserved correctly (380ms and 380ms)
- No buffer delay resets
- **EOT not needed** - natural flow maintained

---

## Scenario 3: Rapid Dits WITH EOT and Reset (Old Behavior)

```
Three separate dits with EOT reset after 672ms (adaptive timeout at 25 WPM)

TX Side:
Time:     0ms   60ms  120ms  792ms  852ms  912ms  1584ms 1644ms 1704ms
          |-----|-----|------|------|------|------|-------|------|------|
Paddle:   [DIT] [UP ]  [EOT→][DIT ] [UP  ]  [EOT→][DIT  ] [UP  ] [EOT→]
Packets:  [DN→] [UP→]        [DN→ ] [UP→ ]        [DN→  ] [UP→ ]

RX Side (100ms buffer, WITH reset on EOT):
Time:     100ms 160ms 220ms  892ms  952ms  1012ms 1684ms 1744ms 1804ms
          |-----|-----|------|------|------|-------|-------|------|------|
Timeline: ═════════════════╪══════════════════════╪════════════════════→
          ^               RESET                  RESET
          Initial buffer   ↓                      ↓
Buffer:   [DIT] [UP ] (gap+wait) [DIT ] [UP ] (gap+wait) [DIT] [UP]
RX Audio: [beep]         (silence)  [beep]     (silence)   [beep]
          
Delays:   100ms initial   672ms EOT + 100ms buffer = 772ms total delay!
```

**Observation:**
- Timeline resets cause **artificial delays**
- User experiences long silences (772ms) between dits
- Makes rapid testing feel broken
- **EOT reset is harmful** for continuous operation

---

## Scenario 4: Message End Detection (Why EOT Exists)

```
Sending "HI" then waiting

TX Side:
Time:     0ms   ...   800ms (H done)  ...   1600ms (I done)  ...  3200ms
          |-----------|-----------------|-------------------|-----------|
Message:  [H = ····] [char space]      [I = ··]            [EOT after 2× word space]
Packets:  [events...] [events...]      [events...]         [EOT→]

RX Application:
Time:     100ms ...   900ms           ...   1700ms          ...  3300ms
          |-----------|-----------------|-------------------|-----------|
Display:  Playing H   Playing I        I complete          [Show "Message Complete"]
                                                            Update statistics
                                                            Reset state validation
```

**Use Cases for EOT:**
1. **Application UI** - Show "Transmission Complete" indicator
2. **Statistics** - Signal end of measurement period
3. **State Reset** - Clear validation errors for next transmission
4. **Session Management** - Know when sender is idle

**NOT for:**
- ❌ Resetting timeline (breaks continuous flow)
- ❌ Clearing buffer timing (creates artificial delays)

---

## Scenario 5: Long Gap (>2 seconds) - Natural Reset

```
Message, long pause, then new message

RX Side:
Time:     0ms   ... 1000ms ... 3500ms (>2sec gap) ... 3600ms
          |-----------|----------|-------------------|-----------|
Buffer:   [Message 1] [complete] (pause > 2 seconds) [Message 2]
Timeline: ═════════════════════╪═══════════════════════════════→
                              AUTO RESET (existing code)
                              ↓
Queue:    [...events...]     [empty]                [new events with fresh buffer]
```

**Existing Code (line 64-72 in cw_receiver.py):**
```python
# Reset if there's a long gap (>2 seconds) between transmissions
if self.last_arrival and (arrival_time - self.last_arrival) > 2.0:
    self.last_event_end_time = None
    # Clear old events from queue
```

**Observation:**
- Buffer already handles long gaps automatically
- Natural reset after 2 seconds of silence
- No EOT needed for timeline management

---

## Scenario 6: Network Jitter on WAN

```
Packets sent at regular intervals, but arrive with jitter

TX Side (Regular timing):
Time:     0ms   60ms  120ms  180ms  240ms
          |-----|-----|------|------|
Packets:  [1 →] [2 →] [3  →] [4  →]

Network (Variable delay):
Delay:    50ms  80ms  45ms   90ms

RX Arrival (Irregular):
Time:     50ms  140ms 165ms  330ms
          |-----|-----|------|------|
Arrive:   [1]   [2]   [3]    [4]

RX Playout (Smooth with buffer):
Time:     150ms 210ms 270ms  330ms  (Timeline maintained)
          |-----|-----|------|------|
Buffer:   [1]   [2]   [3]    [4]    (Playout relative to previous)
Audio:    [beep][beep][beep] [beep] (Smooth, no gaps)

Buffer Math:
  Pkt 1: Arrive 50ms,  playout 150ms  = 100ms buffer
  Pkt 2: Arrive 140ms, playout 210ms  = 70ms buffer (still safe)
  Pkt 3: Arrive 165ms, playout 270ms  = 105ms buffer (good)
  Pkt 4: Arrive 330ms, playout 330ms  = 0ms! Timeline shift needed!
         → Shifts to 340ms (now + 10ms margin)
```

**Observation:**
- Buffer absorbs jitter up to buffer_ms
- Timeline shifts when packet arrives late
- EOT irrelevant - this is ongoing transmission

---

## Summary: EOT Purpose and Behavior

### ✅ **KEEP EOT FOR:**
1. **Signaling end of transmission** - Apps know when message is complete
2. **Resetting state validation** - Clear DOWN/UP expectation for next message
3. **Statistics boundaries** - Mark measurement periods
4. **Session management** - Detect idle vs. active transmission

### ❌ **DON'T USE EOT FOR:**
1. **Timeline resets** - Breaks continuous operation
2. **Buffer clearing** - Creates artificial delays
3. **Timing management** - Buffer already handles gaps naturally

### 📋 **Current Implementation (Correct):**

**EOT Reset Behavior:**
```python
def drain_buffer(self, timeout=2.0):
    # Wait for queue to empty
    while not self.event_queue.empty() and (time.time() - start) < timeout:
        time.sleep(0.01)
    
    # Reset ONLY state validation
    self.expected_key_state = None
    
    # Do NOT reset timeline:
    # self.last_event_end_time = None  ← REMOVED
    # self.last_arrival = None          ← REMOVED
```

**Natural Gap Handling (Already exists):**
```python
# In add_event():
if self.last_arrival and (arrival_time - self.last_arrival) > 2.0:
    self.last_event_end_time = None  # Reset for natural gap
    # Clear old events
```

---

## Recommendations

### For Localhost Testing:
```bash
# TX sidetone only (no echo, instant feedback)
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0 --sidetone-freq 700
python3 cw_receiver.py --no-sidetone --buffer 50

# Or disable RX entirely, just use TX sidetone
python3 cw_usb_key_sender.py localhost iambic-b 25 /dev/ttyUSB0 --sidetone-freq 700
# (no receiver needed for local practice)
```

### For WAN Operation:
```bash
# TX sidetone for immediate feedback, RX for monitoring remote side
python3 cw_usb_key_sender.py remote.example.com iambic-b 20 /dev/ttyUSB0 --sidetone-freq 600
python3 cw_receiver.py --buffer 150  # RX monitors incoming from others
```

### For Receiving Only:
```bash
# Just RX sidetone, no TX
python3 cw_receiver.py --buffer 100 --sidetone-freq 700
```

---

## Conclusion

**EOT is necessary** but only for **signaling**, not timing management:
- ✅ Tells applications "message complete"
- ✅ Resets state validation
- ✅ Marks statistics boundaries
- ❌ Should NOT reset buffer timeline
- ❌ Should NOT clear timing state

The protocol works correctly with EOT as a **logical marker**, not a **timing control**. The adaptive EOT timeout (14 dits) is good for quickly signaling end of transmission, but the buffer should maintain its timeline across EOT boundaries for smooth continuous operation.
