# TCP vs UDP for Morse Code Transmission - Comparative Analysis

## Executive Summary

This document compares TCP and UDP implementations for real-time CW (Morse code) transmission, focusing on timing accuracy, manual keying handling, and network performance trade-offs.

**TL;DR Recommendation:** **UDP with jitter buffer** is superior for real-time CW transmission due to better latency characteristics and more predictable behavior with packet loss.

---

## 1. Protocol Comparison

### 1.1 TCP Implementation (protocol-TCP)

**Transport:** TCP stream
- Guaranteed delivery
- In-order packet arrival
- Automatic retransmission
- Connection-oriented

**CRITICAL: Packet Sending Strategy**
```
TCP v1 (Wait-for-Completion): Waits for key-up before sending
TCP v2 (Immediate Send):      Sends immediately like UDP

TCP v2 example:

Operator keys:  ___UP___/‾‾‾‾DOWN(150ms)‾‾‾‾\___UP___
                        ↑                    ↑
Packets sent:           |                    |
                        |                    └─ Send: UP, 150ms  
                        └────────────────────── Send: DOWN, <prev_up_duration>

With good network:
Latency = Network delay + Jitter buffer
        = 50ms + 100ms = 150ms (same as UDP!)
```

**Packet format:**
```python
# Sent AFTER key-up - contains completed event
{
    "state": "DOWN",      # Event that just finished
    "duration_ms": 150    # How long it lasted
}
```

**Advantages:**
- Complete duration measured before sending
- One packet per element (lowest packet rate)
- Simple implementation
- No first-packet handling issues

**Disadvantages:**
- ❌ **MAJOR: Variable latency = element duration + network delay**
- ❌ 60ms dit → 110ms latency, 180ms dah → 230ms latency
- ❌ Long word spaces (420ms) add 420ms latency!
- ❌ Unpredictable feedback timing (confuses operator rhythm)
- ❌ Head-of-line blocking: Single lost packet blocks ALL subsequent packets
- ❌ Retransmission latency: Adds full RTT (50-200ms) to playback
- ❌ Bufferbloat: TCP congestion control can introduce large, variable delays

### 1.2 UDP Implementation (protocol)

**Transport:** UDP datagrams
- Best-effort delivery
- No guaranteed order
- No retransmission
- Connectionless

**CRITICAL: Packet Sending Strategy**
```
Both TCP and UDP can send IMMEDIATELY on every state change:

Operator keys:  ___UP___/‾‾‾‾DOWN(150ms)‾‾‾‾\___UP___
                        ↑                    ↑
Packets sent:           |                    |
                        |                    └─ Send: UP, 150ms
                        └────────────────────── Send: DOWN, <prev_up_duration>

Note: Packets encode the duration of the state that JUST ENDED

Latency = Network delay + Jitter buffer (constant with good network!)
        = 50ms + 100ms = 150ms
```

**Packet format:**
```python
# Sent IMMEDIATELY on state change - describes previous event
# On key-down:
{
    "state": "UP",        # Previous event (space)
    "duration_ms": 60     # How long the space was
}

# On key-up:
{
    "state": "DOWN",      # Previous event (key press)
    "duration_ms": 150    # How long the press was
}
```

**Advantages:**
- ✅ **Constant, minimal latency** (independent of element duration)
- ✅ Immediate feedback on every state change
- ✅ Predictable timing (operator can adapt to fixed delay)
- ✅ No head-of-line blocking: Lost packets don't affect subsequent ones
- ✅ Tunable jitter buffer provides consistent timing
- ✅ Lost packet handling: Creates gap but continues playback

**Disadvantages:**
- Two packets per complete element (2x packet rate vs TCP)
- Packet loss creates timing gaps
- Requires sequence number tracking
- More complex implementation (jitter buffer needed)
- First packet needs special handling (no previous event)

---

## 2. Critical Timing Differences

### 2.1 Packet Sending: Both Can Send Immediately!

**IMPORTANT CORRECTION:** Both TCP and UDP **can** send packets immediately on state changes. This is NOT the fundamental difference.

**The real difference is what happens during PACKET LOSS:**

**TCP (Wait-for-Completion):**
```
Time:     0ms          150ms         200ms
          │            │             │
Key:      DOWN─────────UP            │
Packet:                └─────────────┴► Sent after key-up
                                     
Receiver hears sidetone: 200ms + network delay later
```

**UDP (Immediate Send):**
```
Time:     0ms          150ms         200ms
          │            │             │
Key:      DOWN─────────UP            │
Packet:   └►           └►            │
          Send UP      Send DOWN     │
          (previous)   (current)     │
                                     
Receiver hears sidetone: Network delay + buffer later (constant)
```

### 2.2 The Real Problem: Late Packets Break Jitter Buffer Scheduling

**With immediate sending (TCP v2 or UDP), both have same latency on good networks:**

| Element | Duration | TCP v2 (no loss) | UDP (no loss) | Winner |
|---------|----------|------------------|---------------|--------|
| **DIT** | 60ms | 50ms + 100ms = 150ms | 50ms + 100ms = 150ms | **TIE** |
| **DAH** | 180ms | 50ms + 100ms = 150ms | 50ms + 100ms = 150ms | **TIE** |
| **All elements** | Any | 150ms (constant) | 150ms (constant) | **TIE** |

**The problem appears during PACKET LOSS:**

```python
# How jitter buffer schedules packets:

def add_event(self, key_down, duration_ms, arrival_time):
    # Schedule relative to previous event end
    playout_time = self.last_event_end_time
    self.last_event_end_time = playout_time + duration_ms / 1000.0
    
    # Check if packet arrived too late
    headroom = playout_time - time.time()
    
    if headroom < 0:
        # PACKET MISSED ITS PLAYOUT TIME!
        # Audio plays for 0ms → gap in playback
        print(f"Late packet! headroom={headroom*1000:.0f}ms")
```

**TCP packet loss timeline:**
```
t=0ms:    PKT1 sent, arrives t=50ms  → scheduled to play at t=150ms ✓
t=20ms:   PKT2 sent → LOST! ❌
t=40ms:   PKT3 sent, arrives t=90ms  → BLOCKED by TCP (waiting for PKT2)
t=60ms:   PKT4 sent, arrives t=110ms → BLOCKED by TCP

t=150ms:  PKT1 plays (duration: 60ms)
t=210ms:  PKT1 finishes, expecting PKT2 to play...
          But PKT2 is lost, PKT3/PKT4 are blocked!
          
t=220ms:  TCP RTO timeout, retransmit PKT2
t=270ms:  PKT2 arrives (200ms late!)
t=270ms:  TCP releases PKT3, PKT4

Jitter buffer receives PKT2 at t=270ms:
  - Should have played at: t=210ms (after PKT1)
  - Current time: t=270ms
  - Headroom: 210ms - 270ms = -60ms (LATE!)
  - Result: Audio plays for 0ms → GAP

Jitter buffer receives PKT3 at t=270ms:
  - Should have played at: t=210ms + 60ms = t=270ms
  - Current time: t=270ms
  - Headroom: 270ms - 270ms = 0ms (barely on time)
  - Result: May play correctly or create gap

PKT4 arrives at t=270ms:
  - Should have played at: t=330ms (after PKT3)
  - Current time: t=270ms  
  - Headroom: 330ms - 270ms = 60ms (OK!)
  - Result: Plays normally
```

**UDP packet loss timeline:**
```
t=0ms:    PKT1 sent, arrives t=50ms  → scheduled to play at t=150ms ✓
t=20ms:   PKT2 sent → LOST! ❌
t=40ms:   PKT3 sent, arrives t=90ms  → NOT BLOCKED (continues!)
t=60ms:   PKT4 sent, arrives t=110ms → NOT BLOCKED

t=90ms:   Jitter buffer sees PKT3 (seq=3, expects seq=2)
          Immediate detection! Insert gap for PKT2
          
t=150ms:  PKT1 plays (duration: 60ms)
t=210ms:  PKT1 finishes
t=210ms:  Insert 60ms gap for missing PKT2 (estimated)
t=270ms:  PKT3 plays (arrived on time!)
t=330ms:  PKT4 plays

All packets arrived with positive headroom:
  - PKT3: Arrived t=90ms, plays t=270ms → headroom=180ms ✓
  - PKT4: Arrived t=110ms, plays t=330ms → headroom=220ms ✓
```

**Key insight:** The problem isn't TCP's sending strategy - it's that TCP's retransmission delay causes packets to **arrive too late** for their scheduled playout time, resulting in 0ms audio playback (gaps).

### 2.3 Impact on Operator Experience

**With good network (0% loss): BOTH protocols perform identically**
```
TCP v2: DIT──DAH────DIT
        150ms 150ms 150ms (constant latency) ✓

UDP:    DIT──DAH────DIT  
        150ms 150ms 150ms (constant latency) ✓

Result: Identical experience, perfect rhythm
```

**With 1% packet loss: TCP degrades dramatically**
```
TCP v2 with loss:
  DIT...[200ms RTO delay + late packets]...gap...DIT
  ↑                                              ↑
  Plays normally                     Late packets play for 0ms (gap)

UDP with loss:
  DIT...[60ms estimated gap]...DIT
  ↑                         ↑
  Plays normally    Insert gap, continue normally

Result: TCP creates unpredictable gaps from late packet arrivals
        UDP creates predictable gaps from missing packets
```

**Human factors:** 
- **TCP problem:** Late packets arrive with negative headroom → audio plays for 0ms → confusing gaps
- **UDP advantage:** Missing packets detected immediately → estimated gap → predictable behavior

### 2.4 The Core Problem: Absolute vs Relative Timing

**Both implementations encode durations in packets:**
```
Packet format: [state: DOWN/UP, duration: Xms]
```

**The challenge:** How to handle the **spaces between transmissions** (when operator pauses between characters/words)?

#### Problem Scenario: Manual Keying

```
Operator keys: DIT (50ms) ... pause 500ms ... DAH (150ms)
                ▲_____▲                        ▲_______▲
                |                              |
              Packet 1                      Packet 2
```

**Question:** Does Packet 2 arrive exactly 500ms after Packet 1?
- **LAN:** Usually yes (±5ms jitter)
- **Internet:** NO! (±50-200ms jitter possible)

### 2.2 TCP Timing Behavior

**On Good Network:**
```
Send:    DOWN 50ms ←500ms pause→ UP 50ms
         ▼                        ▼
Receive: DOWN 50ms ←~500ms→      UP 50ms  ✓ Good
```

**On Packet Loss:**
```
Send:    DOWN 50ms ←500ms pause→ UP 50ms
         ▼          [LOST]       ▼ [blocked until retransmit]
Receive: DOWN 50ms ←←←800ms→→→   UP 50ms  ✗ Wrong timing!
```

**Problem:** TCP retransmission delay is **indistinguishable** from operator pause.

### 2.3 UDP with Jitter Buffer (Relative Timing)

**Jitter Buffer Algorithm:**
```python
# Each event starts when previous event ENDS (preserves tempo)
event_start_time = last_event_end_time
event_end_time = event_start_time + duration_from_packet
```

**Key insight:** Duration is encoded in packet, not derived from arrival times!

**On Good Network:**
```
Send:    DOWN 50ms ←500ms pause→ UP 50ms
         ▼  (buf)                ▼  (buf)
Receive: DOWN 50ms ←500ms buf→   UP 50ms  ✓ Perfect
```

**On Packet Loss:**
```
Send:    DOWN 50ms ←500ms pause→ DAH 150ms
         ▼  (buf)   [LOST]       ▼  (buf)
Receive: DOWN 50ms ←gap→         DAH 150ms  ⚠ Gap, but correct duration
```

**Behavior:**
- Lost packet creates gap (receiver sees DOWN→DOWN error)
- Subsequent elements play at **correct duration** (150ms dah is still 150ms)
- Operator notices gap, can repeat if needed
- Better than TCP's arbitrary delay distortion

---

## 3. Manual Keying and Spacing Handling

### 3.1 The Challenge of Human Timing

**Perfect machine timing (20 WPM):**
```
DIT: 60ms
DAH: 180ms
Element space: 60ms
Character space: 180ms
Word space: 420ms
```

**Actual human timing (straight key):**
```
DIT: 50-70ms (±10ms variation)
DAH: 150-210ms (±30ms variation)
Element space: 40-80ms
Character space: 150-250ms (highly variable!)
Word space: 300-600ms (even more variable!)
```

**The "fist":** Each operator has unique timing characteristics that must be preserved.

### 3.2 Spacing Detection Strategies

Both protocols face the same challenge: **When does a pause become a character/word space?**

#### Strategy 1: Timeout-Based (Simple)

```python
# Wait for silence threshold
if silence_duration > 3 * dit_duration:
    output_character_space()
if silence_duration > 7 * dit_duration:
    output_word_space()
```

**Problem:** Requires WPM estimation from live input.

#### Strategy 2: Adaptive Threshold

```python
# Track recent element durations
recent_dits = [52, 48, 55, 50, 53]
avg_dit = 51.6ms

# Thresholds adapt to operator's speed
char_space_threshold = avg_dit * 2.5  # ~129ms
word_space_threshold = avg_dit * 6.0  # ~310ms
```

**Advantage:** Adapts to operator speed changes.

#### Strategy 3: Statistical Analysis

```python
# Build histogram of space durations
spaces = [45, 48, 52, 180, 175, 188, 450, 460, 440]
         └element┘  └character┘    └word┘

# Detect clusters → classify
cluster_1 (40-60ms):   element spaces
cluster_2 (170-190ms): character spaces  
cluster_3 (440-460ms): word spaces
```

**Advantage:** Most robust for irregular timing.

### 3.3 Recommended Approach: Hybrid

```python
class AdaptiveSpacingDetector:
    def __init__(self):
        self.dit_history = []
        self.space_history = []
        
    def process_element(self, key_down, duration_ms):
        if key_down:
            # Track dit/dah durations
            self.dit_history.append(duration_ms)
            self.update_thresholds()
        else:
            # Classify space
            space_type = self.classify_space(duration_ms)
            return space_type
    
    def update_thresholds(self):
        """Adaptive thresholds based on recent elements"""
        if len(self.dit_history) < 5:
            return  # Need more data
        
        # Use median of recent elements (robust to outliers)
        recent = self.dit_history[-20:]
        dits = [d for d in recent if d < 100]  # Filter out dahs
        
        if dits:
            median_dit = sorted(dits)[len(dits)//2]
            self.char_space_threshold = median_dit * 2.5
            self.word_space_threshold = median_dit * 6.0
    
    def classify_space(self, duration_ms):
        """Classify space as element/character/word"""
        if duration_ms < self.char_space_threshold:
            return "element"
        elif duration_ms < self.word_space_threshold:
            return "character"
        else:
            return "word"
```

**Key features:**
- Adapts to operator speed in real-time
- Uses median (robust to outliers)
- Requires 5+ elements for accurate threshold
- Works with irregular timing

---

## 4. Network Performance Analysis

### 4.1 CW Bandwidth Characteristics

**Extremely low data rate makes transmission instant:**

```python
# Typical CW at 20 WPM
Events per second: ~3.3 (key down + key up)
Packet size: 30 bytes (header + payload)
Bandwidth: 3.3 × 30 bytes = 100 bytes/sec = 800 bits/sec

Compared to network capacity:
- LAN (100 Mbps):      125,000x faster than CW
- Home internet (50 Mbps): 62,500x faster than CW

Packet transmission time:
- On 100 Mbps: 30 bytes × 8 / 100,000,000 = 0.0024ms
- On 1 Mbps:   30 bytes × 8 / 1,000,000   = 0.24ms

Conclusion: Transmission time is NEGLIGIBLE!
```

**Key insight:** Network has massive excess capacity. Packet loss recovery is **NOT** limited by bandwidth, but by **TCP's loss detection algorithm (RTO timeout)**.

### 4.2 Latency Comparison (Both with Jitter Buffer)

**Corrected analysis assuming both protocols use 150ms jitter buffer:**

| Scenario | TCP v2 + Buffer | UDP + Buffer | Notes |
|----------|-----------------|--------------|-------|
| **No loss** | 150ms (constant) | 150ms (constant) | **TIE** ✓ |
| **1% loss (single)** | 150ms + **70-200ms pause** | 150ms + **60ms gap** | UDP better |
| **1% loss (burst)** | 150ms + **200-300ms pause** | 150ms + **180ms gap** | UDP better |
| **5% loss** | 150ms + **500-1000ms pauses** | 150ms + **300ms gaps** | UDP much better |

**Critical difference:** Not transmission speed (negligible), but:
1. **TCP RTO timeout:** 200-1000ms to detect loss
2. **Head-of-line blocking:** Already-arrived packets can't play
3. **Variable disruption:** Pause duration depends on timing

### 4.3 TCP Retransmission Delay Breakdown

**Why does TCP cause 70-200ms gaps when transmission is instant?**

```python
# TCP retransmission has TWO components:

1. Loss Detection (RTO timeout):     200-1000ms  ← THE PROBLEM!
2. Retransmission + propagation:    0.002ms + 50ms RTT = 50ms

Total TCP delay: ~250-1050ms (dominated by RTO)

# RTO calculation (RFC 6298):
RTO = SRTT + max(G, K×RTTVAR)

Where:
  SRTT   = Smoothed RTT (~50ms typical)
  RTTVAR = RTT variance (~20ms)
  K      = 4 (RFC constant)
  G      = Clock granularity (10ms)
  
Example:
RTO = 50ms + max(10ms, 4×20ms) = 50ms + 80ms = 130ms
Minimum RTO per RFC: 200ms

Final RTO: max(130ms, 200ms) = 200ms
```

**Why so conservative?**
- TCP must distinguish lost packets from delayed packets
- Too aggressive → false alarms (unnecessary retransmits)
- Too slow → poor recovery
- Compromise: Wait 2× RTT or 200ms minimum

**Example timeline with 1% loss:**

```
Scenario: PKT5 lost, 50ms RTT, 200ms RTO, both protocols use 150ms buffer

━━━━━━ TCP v2 + Jitter Buffer ━━━━━━
t=0ms:    PKT1-4 sent, arrive, buffered
t=80ms:   PKT5 sent ──→ LOST! ❌
t=100ms:  PKT6 sent ──→ arrives t=150ms → BLOCKED (waiting for PKT5)
t=120ms:  PKT7 sent ──→ arrives t=170ms → BLOCKED
t=140ms:  PKT8 sent ──→ arrives t=190ms → BLOCKED
t=260ms:  PKT4 finishes playing

t=280ms:  RTO expires! (200ms after sending PKT5)
          TCP detects loss, retransmits PKT5
          
t=280ms:  PKT5 retransmit sent (0.002ms transmission)
t=330ms:  PKT5 arrives (50ms RTT)
t=330ms:  TCP releases PKT5, PKT6, PKT7, PKT8 to jitter buffer

Gap duration: t=330ms - t=260ms = 70ms pause

━━━━━━ UDP + Jitter Buffer ━━━━━━
t=0ms:    PKT1-4 sent, arrive, buffered
t=80ms:   PKT5 sent ──→ LOST! ❌
t=100ms:  PKT6 sent ──→ arrives t=150ms
t=150ms:  Jitter buffer sees seq=6, expects seq=5 → IMMEDIATE detection!
          Estimate PKT5 duration from context (~60ms)
          Insert gap, continue with PKT6

t=260ms:  PKT4 finishes playing
t=260ms:  Insert 60ms gap for missing PKT5
t=320ms:  PKT6 plays (no blocking!)
t=380ms:  PKT7 plays
t=440ms:  PKT8 plays

Gap duration: 60ms (estimated)
```

**Key differences:**
1. **Detection speed:** TCP waits 200ms (RTO), UDP detects immediately (sequence #)
2. **Blocking:** TCP blocks PKT6-8, UDP plays them normally
3. **Gap size:** TCP 70-200ms (varies with timing), UDP 60ms (consistent)

### 4.4 Why Can't TCP Use Fast Retransmit?

**TCP has "fast retransmit" (3 duplicate ACKs) but it doesn't work for CW:**

```python
# Fast retransmit requires 3 duplicate ACKs
# But CW sends packets SLOWLY (~3 packets/second)

t=0ms:    Send PKT1
t=333ms:  Send PKT2  ← 333ms between packets!
t=666ms:  Send PKT3  ← Can't get 3 ACKs fast enough

# By the time 3 packets could generate duplicate ACKs,
# RTO timeout (200ms) has already fired!
```

**Fast retransmit is designed for bulk data transfers** (many packets in flight), not real-time applications with low data rates.

### 4.5 Latency Summary (Corrected)

**With 1% packet loss, 50ms RTT, both using 150ms jitter buffer:**

```
TCP v2 disruption per lost packet:
  - RTO detection:   200ms
  - Retransmit:      50ms RTT
  - Gap in playback: 70-200ms (varies)
  - Blocks future:   Yes (head-of-line blocking)
  
UDP disruption per lost packet:
  - Detection:       Immediate (seq check)
  - Retransmit:      None
  - Gap in playback: 60ms (estimated)
  - Blocks future:   No (continues normally)

At 20 WPM with 1% loss:
  - Expected losses: ~2 packets/minute
  - TCP disruption:  ~140-400ms/minute (variable)
  - UDP disruption:  ~120ms/minute (predictable)
```

**Analysis:**
- UDP has higher baseline latency (jitter buffer)
- TCP latency becomes **unpredictable** with packet loss (RTO timeout)
- UDP latency stays **consistent** regardless of loss
- **Transmission speed is NOT the issue** (instant on modern networks)
- **RTO timeout is the killer** (200ms minimum detection delay)

### 4.6 Jitter Handling

**Both protocols should use jitter buffers for real-time CW!**

**TCP v2 + Jitter Buffer:**
- Jitter is absorbed by application-level buffer (recommended: 50-150ms)
- Smooths out arrival time variations
- BUT: Can't prevent head-of-line blocking from packet loss

**UDP + Jitter Buffer:**
- Jitter is absorbed by application-level buffer (recommended: 100-150ms)
- Smooths out arrival time variations
- Packet loss doesn't block subsequent packets

**Example: 100ms jitter on internet link**

TCP v2 with 150ms buffer:
```
Packet 1 arrives: t=0ms    → Buffer, play at t=150ms
Packet 2 arrives: t=550ms  → Buffer, play at t=210ms (after PKT1's 60ms)
Packet 3 arrives: t=700ms  → Buffer, play at t=770ms (after PKT2's 500ms)

Result: Smooth playback, jitter absorbed
BUT: If PKT2 lost → 200ms RTO delay + head-of-line blocking
```

UDP with 150ms buffer:
```
Packet 1 arrives: t=0ms    → Buffer, play at t=150ms
Packet 2 arrives: t=550ms  → Buffer, play at t=210ms (after PKT1's 60ms)
Packet 3 arrives: t=700ms  → Buffer, play at t=770ms (after PKT2's 500ms)

Result: Smooth playback, jitter absorbed
AND: If PKT2 lost → immediate detection, 60ms gap, no blocking
```

### 4.7 Packet Loss Characteristics

**Internet packet loss patterns:**
- Typically **bursty** (multiple consecutive packets)
- Often due to congestion (bufferbloat)
- 1-5% loss is common on residential connections

**TCP v2 with burst loss (3 consecutive packets):**
```
Send: PKT1 PKT2 PKT3 PKT4 PKT5
      ✓    ✗    ✗    ✗    ✓

Timeline:
t=0ms:    PKT1 arrives, buffered
t=20ms:   PKT2 sent → LOST
t=40ms:   PKT3 sent → LOST
t=60ms:   PKT4 sent → LOST
t=80ms:   PKT5 sent, arrives t=130ms → BLOCKED

t=220ms:  RTO expires for PKT2 (200ms after sending)
t=220ms:  Retransmit PKT2
t=270ms:  PKT2 arrives
t=270ms:  RTO expires for PKT3
t=270ms:  Retransmit PKT3
t=320ms:  PKT3 arrives
t=320ms:  RTO expires for PKT4
t=320ms:  Retransmit PKT4
t=370ms:  PKT4 arrives
t=370ms:  TCP releases PKT2, PKT3, PKT4, PKT5 together

Result: PKT5 blocked for 240ms waiting for PKT2-4 retransmits
Gap: 200-300ms pause in playback
```

**UDP with burst loss (3 consecutive packets):**
```
Send: PKT1 PKT2 PKT3 PKT4 PKT5
      ✓    ✗    ✗    ✗    ✓

Timeline:
t=0ms:   PKT1 arrives, buffered, plays at t=150ms
t=80ms:  PKT5 arrives (seq=5, expects seq=2)
         Immediate detection! Insert gaps for PKT2-4
         Estimate ~60ms per packet = 180ms gap
t=210ms: PKT1 finishes (60ms duration)
t=210ms: Insert 180ms gap for PKT2-4
t=390ms: PKT5 plays (no blocking!)

Result: PKT5 plays on schedule after estimated gap
Gap: 180ms estimated gap (predictable)
```

**Verdict:** 
- TCP: Variable pause (200-300ms) due to RTO timeouts, head-of-line blocking
- UDP: Predictable gap (180ms) based on estimated durations, no blocking
- **UDP degradation is more graceful** (brief gap vs long pause)

---

## 5. Implementation Recommendations

### 5.1 Best Practices for UDP Implementation

#### A. Jitter Buffer Sizing

```python
# Rule of thumb: 2x expected jitter
lan_buffer = 50ms      # Local network (~10-20ms jitter)
internet_buffer = 150ms # Internet (~50-100ms jitter)
satellite_buffer = 300ms # High latency links

# Adaptive sizing based on measured jitter
def calculate_buffer_size(jitter_measurements):
    p95_jitter = percentile(jitter_measurements, 95)
    buffer_size = p95_jitter * 2
    return max(50, min(buffer_size, 300))  # Clamp 50-300ms
```

#### B. Relative Timing (Critical!)

```python
# CORRECT: Relative timing (preserves tempo)
class JitterBuffer:
    def add_event(self, key_down, duration_ms, arrival_time):
        # Schedule based on when PREVIOUS event ends
        playout_time = self.last_event_end_time
        self.last_event_end_time = playout_time + duration_ms / 1000.0
        
        # Add to queue
        self.queue.put((playout_time, key_down, duration_ms))
```

```python
# WRONG: Absolute timing (distorted by jitter)
class BadJitterBuffer:
    def add_event(self, key_down, duration_ms, arrival_time):
        # DON'T DO THIS! Arrival time includes network jitter
        playout_time = arrival_time + buffer_delay
        self.queue.put((playout_time, key_down, duration_ms))
```

#### C. State Validation

```python
# Track expected state to detect packet loss
expected_state = None  # None, True (DOWN), False (UP)

def process_event(key_down, duration_ms):
    # Validate state transition
    if expected_state is not None and key_down == expected_state:
        print(f"ERROR: Invalid transition - got {key_down} twice")
        # Log error but continue playback
    
    expected_state = key_down  # Update expected state
    play_audio(key_down, duration_ms)
```

#### D. End-of-Transmission Handling

```python
# Special packet to signal transmission end
def send_eot_packet():
    packet = create_packet(break_request=True)
    sock.sendto(packet, dest)

def on_receive_eot():
    # Drain jitter buffer (play remaining events)
    jitter_buffer.drain(timeout=2.0)
    
    # Don't reset timing base - allows continuous operation
    # Only reset after long silence (>2 seconds)
```

### 5.2 TCP Implementation Considerations

If you must use TCP (e.g., firewall restrictions):

#### A. Disable Nagle's Algorithm

```python
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
```

**Reason:** Nagle's algorithm batches small packets, adding 40-200ms delay.

#### B. Set TCP Keepalive

```python
sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
```

**Reason:** Detect broken connections faster.

#### C. Use Small Send Buffer

```python
# Limit buffering to reduce latency
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
```

#### D. Still Use Jitter Buffer on Receiver

```python
# Even with TCP, network jitter exists!
# Use small buffer (20-50ms) to smooth out variations
jitter_buffer = JitterBuffer(buffer_ms=30)
```

**Reason:** TCP guarantees order, not timing. You still need to smooth out arrival variations.

### 5.3 Hybrid Approach (Recommended)

Use **both** protocols for different purposes:

```
UDP (port 7355):  Real-time CW keying events (latency-critical)
TCP (port 7356):  Control messages (reliability-critical)
    - Frequency changes
    - Mode changes
    - Text chat
    - Connection management
```

**Benefits:**
- UDP for real-time data (where old data is worthless)
- TCP for control data (where reliability matters)
- Best of both worlds

---

## 6. Timing Solutions for Manual Keying

### 6.1 Problem Statement

Manual keying introduces **variable spacing** that must be preserved:

```
Perfect machine:   DIT SPACE DIT SPACE DAH
                   60ms 60ms 60ms 60ms 180ms

Human operator:    DIT SPACE DIT  SPACE  DAH
                   52ms 68ms 55ms 45ms  175ms
                         ↑        ↑
                     variations are intentional (the "fist")
```

**Requirement:** Preserve the operator's timing character while handling network imperfections.

### 6.2 Solution 1: Duration Encoding (Implemented)

**Approach:** Encode duration in each packet, not derived from arrival times.

```python
# Sender side
def on_key_event(key_down):
    duration_ms = time_since_last_event()
    packet = create_packet(key_down, duration_ms)
    send_udp(packet)
```

**Receiver side (relative timing):**
```python
def on_packet_receive(key_down, duration_ms):
    # Schedule event relative to previous event end
    start_time = last_event_end
    end_time = start_time + duration_ms
    
    schedule_playout(start_time, key_down, duration_ms)
    last_event_end = end_time
```

**Result:** Network jitter doesn't affect timing - duration comes from packet, not network!

### 6.3 Solution 2: Adaptive Buffer for Manual Keying

**Challenge:** How to distinguish manual pause from network delay?

**Approach:** Detect transmission gaps and reset buffer state.

```python
class AdaptiveJitterBuffer:
    def add_event(self, key_down, duration_ms, arrival_time):
        # Detect long gap (>2 seconds) - new transmission
        if self.last_arrival and (arrival_time - self.last_arrival) > 2.0:
            self.reset_buffer()  # New transmission starts
        
        # Normal relative timing
        if self.last_event_end is None:
            # First event - add buffer delay
            playout_time = arrival_time + self.buffer_ms / 1000.0
        else:
            # Subsequent events - relative timing
            playout_time = self.last_event_end
        
        # Handle late events (adaptive shift)
        if playout_time < time.time():
            playout_time = time.time() + 0.01  # Shift forward
        
        self.schedule_playout(playout_time, key_down, duration_ms)
        self.last_event_end = playout_time + duration_ms / 1000.0
        self.last_arrival = arrival_time
```

**Key features:**
- Resets on long gaps (new transmission)
- Maintains relative timing within transmission
- Adapts to late packets (shifts forward)
- Preserves operator's timing variations

### 6.4 Solution 3: Statistical Smoothing (Advanced)

For extremely noisy manual keying, use statistical filtering:

```python
class TimingFilter:
    def __init__(self, window_size=5):
        self.element_history = []
        self.space_history = []
    
    def filter_duration(self, duration_ms, is_key_down):
        """Apply median filter to reduce extreme outliers"""
        if is_key_down:
            history = self.element_history
        else:
            history = self.space_history
        
        history.append(duration_ms)
        if len(history) > window_size:
            history.pop(0)
        
        # Use median of recent values
        if len(history) >= 3:
            filtered = sorted(history)[len(history)//2]
        else:
            filtered = duration_ms
        
        return filtered
```

**Caution:** Only use for very noisy inputs - can distort operator's "fist"!

---

## 7. Practical Recommendations

### 7.1 Quick Decision Matrix

| Use Case | Recommended Protocol | Buffer Size | Notes |
|----------|---------------------|-------------|-------|
| **LAN training** | UDP | 20-50ms | Low latency, minimal jitter |
| **Internet good** | UDP | 100-150ms | Standard home internet |
| **Internet poor** | UDP | 150-250ms | High jitter, packet loss |
| **Firewall/NAT** | TCP + UDP fallback | 30ms (TCP) | Port forwarding may be needed |
| **Satellite** | UDP | 250-400ms | Extreme latency/jitter |
| **Contest/DX** | UDP | 100ms | Balance of latency/quality |

### 7.2 Testing Procedure

To compare TCP vs UDP on your network:

```bash
# Terminal 1: Start UDP receiver
cd /home/tomas/Documents/Projekt/CW/protocol/test_implementation
python3 cw_receiver.py --jitter-buffer 100

# Terminal 2: Start TCP receiver  
cd /home/tomas/Documents/Projekt/CW/protocol-TCP/test-implementation
python3 tcp_receiver.py  # (hypothetical)

# Terminal 3: Send test pattern with simulated jitter
python3 test_jitter_buffer.py --jitter 50 --host localhost --port 7355
```

**Metrics to compare:**
- Latency (time from send to audio)
- Timing accuracy (compare received vs sent durations)
- Behavior under packet loss (use `tc` to simulate)

### 7.3 Measuring Timing Accuracy

```bash
# Add artificial packet loss
sudo tc qdisc add dev lo root netem loss 5%

# Send test pattern
python3 cw_auto_sender.py --message "PARIS PARIS" --wpm 20

# Compare timing on both receivers
# UDP: Should show gaps but correct element durations
# TCP: May show distorted timing due to retransmission delays
```

---

## 8. Conclusion

### 8.1 Summary of Findings

**TCP Drawbacks for Real-Time CW:**
- ❌ Head-of-line blocking introduces unpredictable delays
- ❌ Retransmission delay indistinguishable from manual pauses
- ❌ No control over buffering behavior
- ❌ Timing distortion under packet loss

**UDP Advantages:**
- ✅ Predictable, tunable latency via jitter buffer
- ✅ Graceful degradation (gaps vs delays)
- ✅ No head-of-line blocking
- ✅ Better for real-time applications

**Manual Keying Handling:**
- ✅ Duration encoding preserves operator timing
- ✅ Relative timing algorithm immune to network jitter
- ✅ Adaptive thresholds handle variable spacing
- ✅ Works identically for TCP and UDP (application layer)

### 8.2 Final Recommendation: Dual-Protocol Architecture

**Use BOTH protocols in parallel for their strengths:**

```
┌─────────────────────────────────────────────────────┐
│  CW Application (Single Process)                     │
├─────────────────────────────────────────────────────┤
│                                                       │
│  Thread 1: UDP Keying Sender (port 7355)   ────────┐│
│  Thread 2: UDP Keying Receiver (port 7355) ────────┤├─► Real-time CW
│  Thread 3: TCP Control Sender (port 7356)  ────────┤│   (immediate send)
│  Thread 4: TCP Control Receiver (port 7356)────────┘│
│                                                       │
│  All running concurrently!                           │
└─────────────────────────────────────────────────────┘
```

**Protocol allocation:**

| Data Type | Protocol | Port | Why? |
|-----------|----------|------|------|
| **Key events** | UDP | 7355 | Constant latency, real-time |
| **PTT events** | UDP | 7355 | Instant on/off |
| **Callsign** | TCP | 7356 | Must be reliable |
| **Frequency** | TCP | 7356 | Critical control data |
| **Text chat** | TCP | 7356 | Can't lose messages |
| **Recordings** | TCP | 7356 | File integrity required |
| **Config updates** | TCP | 7356 | Must be reliable |

**Benefits of dual-protocol approach:**
1. ✅ UDP real-time performance for keying (constant 150ms latency)
2. ✅ TCP reliability for control data (won't lose callsigns)
3. ✅ Independent failure domains (keying works if TCP drops)
4. ✅ No blocking between protocols (control msg doesn't delay CW)
5. ✅ Industry standard (VoIP uses RTP+SIP, gaming uses UDP+TCP)

**Example timing with parallel protocols:**
```
Time:     0ms        50ms       100ms      150ms      200ms
          │          │          │          │          │
UDP:      DIT───────►│◄─────────DAH──────────────────►│
          │          │          │          │          │
TCP:      │     Callsign="SM5ABC"         │          │
          │          │          │  Chat: "73 de OP"  │
          │          │          │          │          │
Both protocols active simultaneously - no interference!
```

**Reference implementation:** 
- `/home/tomas/Documents/Projekt/CW/protocol/test_implementation/`
- UDP keying: `cw_protocol.py`, `cw_receiver.py`, `cw_sender.py`
- TCP control: Can be added alongside UDP (see section 8.2.1)

### 8.2.1 Implementing Dual-Protocol Architecture

**Example implementation:**
```python
import socket
import threading
import time
from cw_protocol import CWProtocol
from cw_sender import CWSender
from cw_receiver import CWReceiver

class DualProtocolCW:
    """CW system using UDP for keying, TCP for control"""
    
    def __init__(self, remote_host, udp_port=7355, tcp_port=7356):
        # UDP for real-time keying
        self.udp_sender = CWSender(remote_host, udp_port)
        self.udp_receiver = CWReceiver(host='0.0.0.0', port=udp_port)
        
        # TCP for control messages
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.connect((remote_host, tcp_port))
        self.tcp_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        # Start both receivers in parallel threads
        self.udp_thread = threading.Thread(
            target=self.udp_receiver.run, daemon=True)
        self.tcp_thread = threading.Thread(
            target=self.tcp_control_loop, daemon=True)
        
        self.udp_thread.start()
        self.tcp_thread.start()
    
    # ========== UDP: Real-time keying ==========
    def send_key_event(self, key_down, duration_ms):
        """Send CW event via UDP - immediate, low latency"""
        self.udp_sender.send_event(key_down, duration_ms)
    
    # ========== TCP: Control messages ==========
    def send_callsign(self, callsign):
        """Send callsign via TCP - reliable delivery"""
        msg = f"CALLSIGN:{callsign}\n"
        self.tcp_socket.send(msg.encode())
    
    def send_frequency(self, freq_hz):
        """Send frequency change via TCP"""
        msg = f"FREQ:{freq_hz}\n"
        self.tcp_socket.send(msg.encode())
    
    def send_chat_message(self, text):
        """Send text chat via TCP"""
        msg = f"CHAT:{text}\n"
        self.tcp_socket.send(msg.encode())
    
    def tcp_control_loop(self):
        """Receive control messages from remote"""
        buffer = b''
        while True:
            data = self.tcp_socket.recv(4096)
            if not data:
                break
            buffer += data
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                self.handle_control_message(line.decode())
    
    def handle_control_message(self, message):
        """Process incoming control messages"""
        if message.startswith("CALLSIGN:"):
            callsign = message.split(":", 1)[1]
            print(f"Remote callsign: {callsign}")
        elif message.startswith("FREQ:"):
            freq = message.split(":", 1)[1]
            print(f"Remote QSY to: {freq} Hz")
        elif message.startswith("CHAT:"):
            text = message.split(":", 1)[1]
            print(f"Remote: {text}")

# Usage example
def main():
    cw = DualProtocolCW(remote_host="192.168.1.100")
    
    # Send callsign via TCP (reliable)
    cw.send_callsign("SM5ABC")
    
    # Send CW via UDP (low latency)
    # Simulate: "CQ"
    cw.send_key_event(True, 60)   # C: dah
    time.sleep(0.06)
    cw.send_key_event(False, 60)  # space
    time.sleep(0.06)
    # ... continue pattern ...
    
    # Send chat via TCP
    cw.send_chat_message("73 de SM5ABC")
```

**Key architectural points:**
1. Both protocols run **simultaneously** in separate threads
2. UDP handles **latency-critical** data (key events)
3. TCP handles **reliability-critical** data (callsign, config)
4. No blocking between protocols
5. Graceful degradation (if TCP fails, UDP keying still works)

**This is NOT:**
- ❌ Use TCP first, fall back to UDP on failure
- ❌ Choose one protocol and stick with it
- ❌ Use TCP for some sessions, UDP for others

**This IS:**
- ✅ Both sockets open at the same time
- ✅ Real-time data always uses UDP
- ✅ Control data always uses TCP
- ✅ Industry-standard pattern (like VoIP: RTP+SIP)

### 8.3 Future Enhancements

1. **Forward Error Correction (FEC)** - Reduce impact of packet loss
   - Reed-Solomon coding
   - ~2x bandwidth increase
   - See: `cw_protocol_fec.py`, `cw_receiver_fec.py`

2. **Adaptive buffer sizing** - Automatic adjustment based on measured jitter
   ```python
   # Monitor arrival jitter
   jitter = measure_jitter(last_10_packets)
   buffer_size = jitter * 2 + safety_margin
   ```

3. **Hybrid timing** - Switch between absolute/relative based on gap detection
   - Short gaps (<500ms): Relative timing
   - Long gaps (>500ms): Reset and use absolute timing

4. **Machine learning** - Predict operator's timing patterns
   - Build model of operator's "fist"
   - Detect and correct anomalies (likely network-induced)

---

## References

1. DL4YHF Remote CW Keyer: https://www.qsl.net/dl4yhf/Remote_CW_Keyer/
2. RFC 3550 (RTP): Real-time Transport Protocol
3. "The Case Against TCP for Real-Time Media" - Van Jacobson
4. This implementation: `/home/tomas/Documents/Projekt/CW/protocol/`

---

**Document Version:** 1.0  
**Date:** December 10, 2025  
**Author:** Analysis based on protocol implementations


---

## Protocol Design Documentation

### Core Documentation
- **[TCP vs UDP Comparison](Doc/TCP_UDP_COMPARISON.md)** - Detailed analysis of protocol choices, timing behavior, and manual keying handling
- **[Quick Reference Guide](Doc/TCP_UDP_QUICK_REFERENCE.md)** - Fast decision tree and configuration examples
- **[Manual Keying Solutions](Doc/MANUAL_KEYING_SOLUTIONS.md)** - How to handle variable timing and spacing from human operators
- **[CW Protocol Specification](Doc/CW_PROTOCOL_SPECIFICATION.md)** - Complete protocol specification and design rationale
- **[Jitter Buffer Implementation](Doc/JITTER_BUFFER_IMPLEMENTATION.md)** - Buffer algorithm and tuning guide

### Key Insights

**Why UDP over TCP for real-time CW?**
- ✅ Predictable latency (jitter buffer controlled)
- ✅ Graceful degradation (gaps vs delays)
- ✅ No head-of-line blocking
- ❌ TCP: retransmission delays distort timing

**How does manual keying work?**
- Duration encoded in packets (measured at sender)
- Relative timing on receiver (immune to network jitter)
- Adaptive spacing detection (handles variable operator timing)
- **Works the same for TCP and UDP** (application-layer solution)

See [Manual Keying Solutions](Doc/MANUAL_KEYING_SOLUTIONS.md) for details.