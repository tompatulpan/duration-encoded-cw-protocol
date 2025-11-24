# CW Protocol Specification for Low-Latency Remote Radio Control

## Executive Summary

This document specifies a robust, low-latency protocol for transmitting Morse code (CW) over IP networks to enable remote radio control with real-time keying response. The protocol prioritizes:

1. **Ultra-low latency** - Critical for responsive sidetone and natural keying feel
2. **Robustness** - Reliable operation over varying network conditions
3. **Efficiency** - Minimal bandwidth usage for LoRa/cellular/satellite links
4. **Accuracy** - Faithful reproduction of original timing and operator style

## Table of Contents

1. [Introduction](#introduction)
2. [Design Requirements](#design-requirements)
3. [Protocol Selection & Analysis](#protocol-selection--analysis)
4. [Recommended Architecture](#recommended-architecture)
5. [Packet Format Specification](#packet-format-specification)
6. [Implementation Guidelines](#implementation-guidelines)
7. [Testing & Validation](#testing--validation)
8. [References](#references)

---

## 1. Introduction

### 1.1 Use Cases

- **Primary**: Remote radio CW keying over local network, internet with computer-to-computer connection. USB might be another option
- **Secondary**: Direct computer-to-radio connection over local network or internat. 
- **Tertiary**: Multiple operators sharing a single remote transmitter

### 1.2 Key Challenges

1. **Latency Budget**: Total round-trip latency must be <100ms for acceptable sidetone
   - Network latency: ~20-50ms (typical internet)
   (- USB/Serial latency: ~2-5ms)
   - Audio latency: ~20-40ms (sound card buffering)
   - Processing overhead: <5ms

2. **Jitter Management**: Network jitter can destroy CW timing
3. **Packet Loss**: Must handle dropped packets gracefully
4. **Bandwidth Constraints**: Some links have severe limitations

---

## 2. Design Requirements

### 2.1 Functional Requirements

**MUST HAVE:**
- Transmit key-up/key-down events with millisecond-accurate timing
- Support speeds from 5 WPM to 60+ WPM (HSCW)
- Work over TCP/IP and UDP
- Preserve operator's "fist" (personal timing characteristics)
- **Generate local sidetone on client side** (mandatory for low latency during TX)
- **Generate peer sidetone on receiving side** (for monitoring and training)
- Support both straight keys and electronic keyers
- Enable client-to-client mode (no radio required for training)

**SHOULD HAVE:**
- Multiple simultaneous users with arbitration
- Break-in capability (interrupt transmitting operator)

**NICE TO HAVE:**
- Text messaging between operators
- Automatic speed detection
- CW decoder output (convert keying to text)
- Recording/playback of practice sessions
- Multi-client training rooms with instructor feedback

### 2.2 Non-Functional Requirements

- **Latency**: <10ms encode/decode overhead
- **Bandwidth**: <10 kbps for CW keying stream
- **CPU**: <5% on modern embedded processors
- **Memory**: <64KB RAM footprint
- **Reliability**: Graceful degradation with packet loss <5%

---

## 3. Protocol Selection & Analysis

### 3.1 Evaluated Protocols

#### 3.1.1 CWCom Protocol (MRX Software)
**Source**: https://github.com/Morse-Code-over-IP/protocol-cwcom

**Format**: Timing-based encoding
```
(-2000, +50, -50, +50, -50, +50, -50, +150)
```
- Positive numbers: Mark duration (ms)
- Negative numbers: Space duration (ms)

**Pros:**
- Simple to implement
- Preserves exact timing
- Human-readable debug format
- Well-established (multiple implementations)

**Cons:**
- Variable packet length
- No built-in error detection
- Relies on TCP ordering
- High overhead for ASCII encoding

**Verdict**: ✅ **Recommended for TCP-based connections**

#### 3.1.2 MOPP (Morse Over Packet Protocol)
**Source**: Morserino-32 project

**Format**: Binary state encoding (2-bit symbols)
```
01 = dit
10 = dah  
00 = end-of-character
11 = end-of-word
```

**Header**: 14 bits (version:2, serial:6, speed:6)

**Pros:**
- Extremely bandwidth-efficient (4 symbols per byte)
- Includes speed metadata
- Serial number for packet ordering
- No zero bytes (string-safe)

**Cons:**
- Requires transcoding from real-time events
- Loses fine timing information
- Word-based batching increases latency
- Complex decode logic

**Verdict**: ⚠️ **Good for bandwidth-constrained links (LoRa), not ideal for real-time keying**

#### 3.1.3 Vail Adapter Protocol
**Source**: https://github.com/Vail-CW/vail-adapter

**Format**: USB HID keyboard events + MIDI control

**Pros:**
- Zero-install on modern OS
- Works in browser without drivers
- Well-tested hardware implementation

**Cons:**
- USB polling latency (~8ms typical)
- Not suitable for direct IP transport
- Requires USB host

**Verdict**: ⚠️ **Excellent for local computer connection, not for network transport**

#### 3.1.4 DL4YHF Remote CW Keyer Protocol
**Source**: https://www.qsl.net/dl4yhf/Remote_CW_Keyer/

**Format**: Custom binary with timing compression
```
Byte format: [K|TTTTTTT]
K = Key state (1=down, 0=up)
T = Timing value (7 bits)

Timing encoding:
0x00-0x1F: Direct milliseconds (0-31ms)
0x20-0x3F: 32 + 4*(value-0x20) ms
0x40-0x7F: 157 + 16*(value-0x40) ms (max 1165ms)
```

**Pros:**
- 1 byte per state change (ultra-efficient)
- Non-linear timing compression
- No zero bytes
- Preserves exact timing within resolution

**Cons:**
- Timing resolution varies (1ms to 16ms)
- Requires multiple bytes for long spaces
- Custom encoding/decoding logic

**Verdict**: ✅ **Best efficiency for real-time keying**

### 3.2 Protocol Comparison Matrix

| Feature | CWCom | MOPP | DL4YHF | Vail |
|---------|-------|------|--------|------|
| Latency | Low | Medium | Low | Low* |
| Bandwidth | Medium | Best | Best | N/A |
| Timing Accuracy | Perfect | Good | Excellent | Perfect* |
| Implementation | Simple | Medium | Medium | Complex |
| Existing Tools | Many | Few | One | Many |
| Error Handling | None | Serial# | None | USB |

\* = Local USB connection only

---

## 4. Recommended Architecture

### 4.1 Hybrid Approach

We recommend a **dual-protocol architecture**:

1. **Primary Real-Time Layer** (DL4YHF-inspired)
   - For CW keying events
   - 1 byte per state change
   - Sent over UDP for minimal latency
   - Sequence numbers for reordering

2. **Secondary Control Layer** (CWCom-compatible)
   - For compatibility with existing tools
   - Control messages (speed change, PTT, break)
   - Sent over TCP for reliability

### 4.2 System Architecture

```
┌─────────────────────┐                        ┌─────────────────────┐
│   CLIENT (TX)       │                        │   SERVER / PEER     │
│                     │                        │                     │
│  ┌───────┐          │                        │  ┌───────┐          │
│  │ Morse │          │                        │  │ Radio │          │
│  │  Key  │          │                        │  │  PTT  │          │
│  └───┬───┘          │                        │  └───▲───┘          │
│      │              │                        │      │              │
│  ┌───▼───────────┐  │   UDP (CW Events)      │  ┌───┴───────────┐ │
│  │ Keyer Logic   │──┼────────────────────────┼─▶│ CW RX Buffer  │ │
│  │ + Encoder     │  │   ◀──(for echo/debug)──┼──│ + Decoder     │ │
│  └───┬───────┬───┘  │                        │  └───┬───────────┘ │
│      │       │      │   UDP (Audio Packets)  │      │             │
│      │       │      │   ◀────────────────────┼──────┤             │
│      │       │      │                        │      │             │
│  ┌───▼────┐ │      │   TCP (Control)        │  ┌───▼────┐        │
│  │TX Side-│ │      │   ◀────────────────────►│  │  Rig   │        │
│  │tone    │ │      │   (Freq, Mode, PTT)    │  │Control │        │
│  │(LOCAL) │ │      │                        │  └────────┘        │
│  └───┬────┘ │      │                        │                     │
│      │      │      │                        │  ┌────────────────┐ │
│  ┌───▼──────▼────┐ │                        │  │ RX Sidetone    │ │
│  │ Audio Mixer  │ │                        │  │ (Peer Monitor) │ │
│  │ (TX+RX tones)│ │                        │  └────────────────┘ │
│  └───┬──────────┘ │                        │                     │
│      │            │                        │                     │
│  ┌───▼──────┐     │   TRAINING MODE:       │  ┌────────────────┐ │
│  │ Speaker  │     │   Client ◄──CW──► Client  │ │   Headphones   │ │
│  │/Headphone│     │   (No radio required)  │  │   /Speaker     │ │
│  └──────────┘     │                        │  └────────────────┘ │
│                   │                        │                     │
└───────────────────┘                        └─────────────────────┘
```

### 4.3 Dual Sidetone Architecture

#### 4.3.1 Client-Side TX Sidetone (Mandatory)

**Critical for low latency**: The TX sidetone MUST be generated locally on the sending client.

**Purpose**:
- Immediate feedback to operator (no network delay)
- Essential for maintaining proper timing and rhythm
- Enables high-speed operation (>30 WPM)

**Implementation Options** (in order of latency):

1. **Hardware sidetone** (0-2ms latency) ⭐ Best
   ```
   External oscillator → Keyed by DTR/RTS → Headphones
   Pros: Zero software latency, perfect reliability
   Cons: Requires external hardware
   ```

2. **Serial port TXD** (3-5ms latency) ⭐ Excellent
   ```
   UART @ 4800 baud with pattern 0xF0 → 480Hz square wave
   UART @ 4800 baud with pattern 0xCE → 960Hz square wave
   ```
   - DL4YHF method - proven in production
   - Requires coupling circuit (resistor + capacitor + speaker)
   - Very low CPU usage
   ```c++
   // Configure serial port as tone generator
   void setupTXDSidetone(SerialPort& port, int frequency) {
       port.setBaudRate(4800);
       port.setDataBits(8);
       port.setStopBits(1);
       
       if (frequency == 480) {
           tonePattern = 0xF0;  // 50% duty cycle
       } else if (frequency == 960) {
           tonePattern = 0xCE;  // Two pulses per byte
       }
   }
   
   void setTXSidetone(bool on) {
       if (on) {
           // Continuously send pattern
           port.write(&tonePattern, 1);
       } else {
           // Send silence (0xFF or 0x00)
           uint8_t silence = 0xFF;
           port.write(&silence, 1);
       }
   }
   ```

3. **Low-latency audio API** (10-20ms latency) ✅ Good
   - Windows: WASAPI exclusive mode
   - Linux: ALSA with small buffer sizes
   - macOS: CoreAudio with low buffer
   ```c++
   // Example: WASAPI low-latency setup
   IAudioClient* audioClient;
   audioClient->Initialize(
       AUDCLNT_SHAREMODE_EXCLUSIVE,
       AUDCLNT_STREAMFLAGS_EVENTCALLBACK,
       bufferDuration_100ns,  // 10ms = 100,000
       bufferDuration_100ns,
       &waveFormat,
       NULL
   );
   ```

4. **Standard audio API** (20-50ms latency) ⚠️ Acceptable for <25 WPM
   - Windows: DirectSound
   - Linux: PulseAudio
   - macOS: CoreAudio default

5. **Never use**: Remote radio's sidetone (round-trip latency 50-200ms) ❌

**Tone Generation Algorithm**:
```c++
class SidetoneGenerator {
private:
    float phase = 0.0f;
    float frequency = 600.0f;  // Hz, configurable
    float sampleRate = 48000.0f;
    float volume = 0.5f;
    
    // Rise/fall envelope to prevent clicks
    float riseTime_ms = 5.0f;
    float fallTime_ms = 5.0f;
    float currentEnvelope = 0.0f;
    
public:
    void generateSamples(float* buffer, int numSamples, bool keyDown) {
        float envelopeTarget = keyDown ? 1.0f : 0.0f;
        float envelopeRate = keyDown ? 
            (1.0f / (riseTime_ms * sampleRate / 1000.0f)) :
            (1.0f / (fallTime_ms * sampleRate / 1000.0f));
        
        for (int i = 0; i < numSamples; i++) {
            // Smooth envelope
            if (currentEnvelope < envelopeTarget) {
                currentEnvelope += envelopeRate;
                if (currentEnvelope > envelopeTarget) 
                    currentEnvelope = envelopeTarget;
            } else if (currentEnvelope > envelopeTarget) {
                currentEnvelope -= envelopeRate;
                if (currentEnvelope < envelopeTarget) 
                    currentEnvelope = envelopeTarget;
            }
            
            // Generate sine wave
            buffer[i] = volume * currentEnvelope * 
                        sinf(2.0f * M_PI * phase);
            
            // Advance phase
            phase += frequency / sampleRate;
            if (phase >= 1.0f) phase -= 1.0f;
        }
    }
};
```

#### 4.3.2 Server/Peer-Side RX Sidetone (Essential for Training)

**Purpose**:
- Monitor remote operator's keying in real-time
- Essential for CW training scenarios
- Debug timing and protocol issues
- Enable client-to-client practice (no radio required)

**Implementation**:
```c++
class PeerSidetoneGenerator {
private:
    SidetoneGenerator generator;
    JitterBuffer keyEventBuffer;
    
public:
    void onCWPacketReceived(CWPacket* pkt) {
        // Buffer events to smooth out network jitter
        keyEventBuffer.addPacket(pkt);
    }
    
    void audioCallback(float* output, int numSamples) {
        // Process buffered key events
        auto events = keyEventBuffer.getEventsForTimeRange(
            currentTime, currentTime + numSamples / sampleRate
        );
        
        for (auto& event : events) {
            int sampleOffset = timeToSample(event.timestamp);
            generator.generateSamples(
                output + sampleOffset,
                numSamples - sampleOffset,
                event.keyDown
            );
        }
    }
};
```

**Configuration Options**:
```yaml
sidetone_rx:
  enabled: true
  mode: "buffered"  # buffered, immediate
  frequency: 700  # Different from TX to distinguish
  volume: 60  # Slightly quieter than TX
  jitter_buffer_ms: 100  # Smooth out network jitter
  
  # For training mode
  training:
    decode_to_text: true  # Show what was sent
    show_timing: true     # Display actual vs ideal timing
    highlight_errors: true  # Audio cue for timing issues
```

#### 4.3.3 Audio Mixing (TX + RX Sidetones)

**Scenario**: Client hears both their own keying AND remote peer's response

```c++
class AudioMixer {
private:
    SidetoneGenerator txTone;  // 600 Hz
    SidetoneGenerator rxTone;  // 700 Hz (different frequency)
    float rxAudio[BUFFER_SIZE];  // Received radio/peer audio
    
public:
    void mixAudio(float* output, int numSamples) {
        // Start with zeros
        memset(output, 0, numSamples * sizeof(float));
        
        // Add TX sidetone (local keying)
        if (localKeyDown) {
            float txBuffer[BUFFER_SIZE];
            txTone.generateSamples(txBuffer, numSamples, true);
            for (int i = 0; i < numSamples; i++) {
                output[i] += txBuffer[i];
            }
        }
        
        // Add RX sidetone (peer keying)
        if (peerKeyingReceived) {
            float rxBuffer[BUFFER_SIZE];
            rxTone.generateSamples(rxBuffer, numSamples, true);
            for (int i = 0; i < numSamples; i++) {
                output[i] += rxBuffer[i] * 0.8f;  // Slightly quieter
            }
        }
        
        // Add received audio (radio or peer voice)
        if (audioStreamEnabled) {
            for (int i = 0; i < numSamples; i++) {
                output[i] += rxAudio[i] * 0.5f;  // Adjust levels
            }
        }
        
        // Final limiter to prevent clipping
        for (int i = 0; i < numSamples; i++) {
            if (output[i] > 1.0f) output[i] = 1.0f;
            if (output[i] < -1.0f) output[i] = -1.0f;
        }
    }
};
```

#### 4.3.4 Training Mode: Client-to-Client

**Use Case**: Two or more operators practicing CW without a radio

**Architecture**:
```
┌─────────────┐            ┌─────────────┐            ┌─────────────┐
│  STUDENT 1  │◄──CW───────┤   SERVER    │◄──CW───────│  STUDENT 2  │
│             │   Events   │  (Relay)    │   Events   │             │
│  Key + RX   │            │             │            │  Key + RX   │
│  Sidetones  │            │ No Radio!   │            │  Sidetones  │
└─────────────┘            └─────────────┘            └─────────────┘
       ▲                          │                          ▲
       │                          │                          │
       └──────────────────────────┴──────────────────────────┘
              Optional: Instructor monitoring/feedback
```

**Server Configuration**:
```yaml
training_mode:
  enabled: true
  radio_output: false  # Disable actual transmitter
  
  # Relay all CW events between clients
  relay_mode: "all_to_all"  # or "instructor_to_students"
  
  # Optional features
  decode_cw: true  # Show text on instructor console
  record_session: true
  playback_at_end: true
  
  scoring:
    enabled: true
    check_timing: true
    accuracy_threshold: 95  # percent
```

**Implementation**:
```c++
class TrainingServer {
private:
    std::vector<Client*> students;
    Client* instructor;
    
public:
    void onCWEventReceived(Client* sender, CWEvent event) {
        // Don't send to radio - this is training!
        
        // Relay to all other clients
        for (auto* client : students) {
            if (client != sender) {
                client->sendCWEvent(event);
            }
        }
        
        // Send to instructor for monitoring
        if (instructor) {
            instructor->sendCWEvent(event, sender->getCallsign());
        }
        
        // Decode for analysis
        if (config.decode_cw) {
            char decoded = cwDecoder.addEvent(event);
            if (decoded) {
                recordTranscript(sender, decoded);
            }
        }
    }
};
```

**Student Client Features**:
```yaml
training_client:
  tx_sidetone:
    enabled: true
    frequency: 600
    
  rx_sidetone:
    enabled: true
    frequency: 700  # Different tone = different operator
    label_tones: true  # Show "You" vs "Peer" on screen
    
  visual_feedback:
    show_own_timing: true
    show_peer_timing: true
    show_decoded_text: true
    
  practice_modes:
    - "echo"           # Repeat what you hear
    - "call_response"  # Instructor sends, you reply
    - "conversation"   # Free-form QSO practice
    - "code_groups"    # Random 5-letter groups
```

---

## 5. Packet Format Specification

### 5.1 CW Keying Packet (UDP)

#### 5.1.1 Header (3 bytes)
```
Byte 0: Protocol Version and Flags
  Bits 7-6: Protocol version (01 = v1)
  Bit  5:   Training mode flag (1 = no radio output)
  Bit  4:   Echo request (ask server to reflect packet)
  Bit  3:   Break request flag
  Bit  2:   PTT state (ignored in training mode)
  Bits 1-0: Keyer mode (00=straight, 01=bug, 10=iambic-A, 11=iambic-B)

Byte 1: Sequence Number (0-255, wrapping)

Byte 2: Client ID (for multi-user scenarios)
        0x00 = Server/Instructor
        0x01-0xFE = Students/Peers
        0xFF = Broadcast to all
```

#### 5.1.2 Payload (variable length, 1-255 bytes)

Each state change encoded as 1 byte:
```
Bit 7: Key State (1=down, 0=up)
Bits 6-0: Timing value (0-127)

Timing Encoding (optimized for CW):
  0x00-0x3F (0-63):   Direct milliseconds (good for 15-60 WPM)
  0x40-0x5F (64-95):  64 + 2*(value-64) ms (64-126ms)
  0x60-0x7F (96-127): 128 + 8*(value-96) ms (128-384ms)
```

**Example - "E" at 20 WPM** (60ms dit):
```
Header: [0x40][0x01][0x42]  // v1, seq=1, client=0x42
Payload: [0xBC][0x3C]       // Key down 60ms, key up 60ms
Total: 5 bytes
```

### 5.2 Control Packet (TCP)

#### 5.2.1 JSON-based (human-readable, debugging)
```json
{
  "type": "control",
  "timestamp": 1234567890,
  "command": "set_freq",
  "value": 14060000
}
```

#### 5.2.2 Binary (production)
```
Byte 0: Message Type
  0x01 = Frequency change
  0x02 = Mode change
  0x03 = Speed change
  0x04 = Request TX permission
  0x05 = Release TX permission
  0x06 = Heartbeat
  0x07 = Enter training mode
  0x08 = Exit training mode
  0x09 = Set RX sidetone parameters
  0x0A = Decoded CW text (for training feedback)
  0x0B = Timing analysis results
  
Bytes 1-N: Type-specific payload
```

#### 5.2.3 Training Mode Control Packets

**Enter Training Mode (0x07)**:
```
Byte 0: 0x07
Byte 1: Mode flags
  Bit 0: Enable CW decode
  Bit 1: Enable timing analysis
  Bit 2: Enable recording
  Bit 3: Echo mode (repeat back)
  Bits 4-7: Reserved
Byte 2: Max students (0 = unlimited)
```

**RX Sidetone Config (0x09)**:
```
Byte 0: 0x09
Byte 1-2: Frequency (Hz, big-endian)
Byte 3: Volume (0-100)
Byte 4: Enable/disable (0x00 or 0x01)
```

**Decoded Text Feedback (0x0A)**:
```
Byte 0: 0x0A
Byte 1: Source client ID
Byte 2: Character count
Byte 3-N: UTF-8 text (decoded CW)
```

**Timing Analysis (0x0B)**:
```
Byte 0: 0x0B
Byte 1: Client ID being analyzed
Byte 2-3: Average WPM (fixed-point: value/10)
Byte 4: Timing accuracy score (0-100)
Byte 5: Dit/Dah ratio deviation (signed, ±50 = ±50%)
```

### 5.3 Audio Packet (UDP or TCP)

- **Codec**: A-Law or μ-Law (8-bit, 8kHz) for efficiency
- **Alternative**: Opus codec (6-12 kbps) for better quality
- **Packet size**: 40ms chunks (320 bytes @ 8kHz)
- **Sequence number**: 2 bytes for reordering
- **Timestamp**: 4 bytes for jitter buffer

---

## 6. Implementation Guidelines

### 6.1 Client-Side Implementation

#### 6.1.1 Key Input Polling
```c++
// Poll at 500Hz (2ms intervals) for accurate timing
void pollKeyInput() {
    static uint32_t lastTime = 0;
    uint32_t currentTime = millis();
    
    bool keyDown = digitalRead(KEY_PIN);
    
    if (keyDown != lastKeyState) {
        uint16_t duration = currentTime - lastTime;
        
        // Send state change packet
        sendCWEvent(keyDown, duration);
        
        // Generate local sidetone
        setTone(keyDown ? SIDETONE_FREQ : 0);
        
        lastKeyState = keyDown;
        lastTime = currentTime;
    }
}
```

#### 6.1.2 Packet Buffering
```c++
// Coalesce rapid changes into single packet
class CWPacketBuffer {
    static const int MAX_EVENTS = 32;
    CWEvent events[MAX_EVENTS];
    int count = 0;
    uint32_t firstEventTime = 0;
    
    void addEvent(bool keyDown, uint16_t duration) {
        if (count == 0) {
            firstEventTime = millis();
        }
        
        events[count++] = {keyDown, duration};
        
        // Send packet if:
        // - Buffer full
        // - >50ms since first event (latency limit)
        // - Key released (end of element)
        if (count >= MAX_EVENTS || 
            millis() - firstEventTime > 50 ||
            (!keyDown && duration > 30)) {
            sendPacket();
        }
    }
};
```

### 6.2 Server-Side Implementation

#### 6.2.1 Jitter Buffer
```c++
// Compensate for network timing variations
class JitterBuffer {
    static const int BUFFER_TIME_MS = 100; // Tune based on network
    
    struct QueuedEvent {
        uint32_t timestamp;
        bool keyDown;
    };
    
    std::priority_queue<QueuedEvent> queue;
    
    void addEvent(bool keyDown, uint32_t networkTimestamp) {
        // Calculate playout time
        uint32_t playoutTime = localTime() + BUFFER_TIME_MS;
        queue.push({playoutTime, keyDown});
    }
    
    void process() {
        uint32_t now = localTime();
        while (!queue.empty() && queue.top().timestamp <= now) {
            auto event = queue.top();
            queue.pop();
            setKeyOutput(event.keyDown);
        }
    }
};
```

#### 6.2.2 Keying Output
```c++
// Hardware interface to radio
void setKeyOutput(bool keyDown) {
    // Method 1: Direct GPIO (fastest, <1ms)
    digitalWrite(CW_KEY_PIN, keyDown);
    
    // Method 2: Serial port DTR/RTS (3-5ms)
    serialPort.setDTR(keyDown);
    
    // Method 3: CI-V command for Icom radios (10-20ms)
    if (keyDown) {
        sendCIVCommand(0x1A, 0x05, 0x00, 0x35, 0x01); // Send CW
    }
}
```

### 6.3 Network Configuration

#### 6.3.1 Firewall/NAT Traversal

**STUN/TURN Support**:
```python
# Use STUN to discover public IP/port
import pystun
nat_type, external_ip, external_port = pystun.get_ip_info()

# If symmetric NAT, use TURN relay
if nat_type == pystun.SymmetricNAT:
    use_turn_server('turn.example.com', 3478)
```

**Port Forwarding** (if static IP available):
- UDP 7355: CW keying data
- TCP 7356: Control channel
- UDP 7357-7358: Audio streams

#### 6.3.2 Quality of Service (QoS)

**DSCP Marking** for prioritization:
```c++
// Set IP packet priority (requires root/admin)
int dscp = 46; // EF (Expedited Forwarding) for CW packets
setsockopt(sock, IPPROTO_IP, IP_TOS, &dscp, sizeof(dscp));
```

**Recommended DSCP values**:
- CW keying: EF (46) - highest priority
- Audio: AF41 (34) - high priority  
- Control: AF21 (18) - medium priority

### 6.4 Error Handling

#### 6.4.1 Packet Loss Recovery
```c++
// Detect lost packets via sequence numbers
void handleCWPacket(CWPacket* pkt) {
    uint8_t expectedSeq = (lastSeqNum + 1) % 256;
    
    if (pkt->seqNum != expectedSeq) {
        int lost = (pkt->seqNum - expectedSeq + 256) % 256;
        
        if (lost < 10) {
            // Insert silence to maintain timing
            insertSilence(lost * PACKET_INTERVAL_MS);
        } else {
            // Too many lost - resync
            resetJitterBuffer();
        }
    }
    
    lastSeqNum = pkt->seqNum;
}
```

#### 6.4.2 Timeout Handling
```c++
// Auto-release key if no packets received
class WatchdogTimer {
    static const int TIMEOUT_MS = 3000;
    uint32_t lastPacketTime = 0;
    
    void update() {
        if (millis() - lastPacketTime > TIMEOUT_MS) {
            // Emergency key-up
            setKeyOutput(false);
            notifyTimeout();
        }
    }
};
```

---

## 7. Testing & Validation

### 7.1 Latency Testing

**Test Setup**:
1. Loopback cable from CW output back to key input
2. Oscilloscope on both signals
3. Measure time delta

**Acceptable Values**:
- Local USB: <10ms
- Same LAN: <30ms
- Internet (<100ms ping): <120ms
- Internet (>100ms ping): User decision

**Test Code**:
```python
import time
import statistics

latencies = []
for i in range(100):
    send_time = time.time()
    send_cw_event(key_down=True)
    receive_cw_event()  # Block until received
    latency = (time.time() - send_time) * 1000
    latencies.append(latency)

print(f"Mean: {statistics.mean(latencies):.1f}ms")
print(f"Stdev: {statistics.stdev(latencies):.1f}ms")
print(f"p99: {sorted(latencies)[99]:.1f}ms")
```

### 7.2 Timing Accuracy

**Test Method**: Record CW sent at various speeds, analyze element timing

```python
# Analyze timing accuracy
def test_timing_accuracy(wpm=20):
    # Expected dit length at 20 WPM: 60ms
    expected_dit = 1200 / wpm
    
    # Send test pattern: "E E E" (5 dits, 4 spaces)
    events = send_and_record_pattern("E E E")
    
    dits = [e.duration for e in events if e.key_down]
    spaces = [e.duration for e in events if not e.key_down]
    
    avg_dit = statistics.mean(dits)
    avg_space = statistics.mean(spaces)
    
    dit_error = abs(avg_dit - expected_dit) / expected_dit * 100
    space_error = abs(avg_space - expected_dit) / expected_dit * 100
    
    assert dit_error < 5%, f"Dit timing error {dit_error:.1f}% exceeds 5%"
    assert space_error < 5%, f"Space timing error {space_error:.1f}% exceeds 5%"
```

### 7.3 Network Stress Testing

**Simulate Poor Network Conditions**:
```bash
# Linux tc (traffic control) to add latency/jitter/loss
tc qdisc add dev eth0 root netem delay 50ms 20ms loss 2%

# Run CW test
./test_cw_protocol --duration 60 --wpm 20

# Remove network impairment
tc qdisc del dev eth0 root netem
```

**Acceptance Criteria**:
- <1% character errors at 2% packet loss
- Graceful degradation up to 5% loss
- Maintain sync with 100ms jitter

### 7.4 Compatibility Testing

**Test Against Reference Implementations**:
1. **CWCom** (Windows client)
2. **MorseKOB** (Python)
3. **DL4YHF Remote CW Keyer** (Windows)
4. **Vail** (Web browser)

**Test Matrix**:
| Client | Server | Protocol | Status |
|--------|--------|----------|--------|
| Our impl. | CWCom | CWCom | Should work |
| Our impl. | Our impl. | Native | Primary |
| Vail | Our impl. | Adapter | Via USB |
| Our impl. | DL4YHF | DL4YHF | Compatible |

---

## 8. References

### 8.1 Reviewed Protocols

1. **CWCom Protocol** (Les Kerr, 2006)
   - https://github.com/Morse-Code-over-IP/protocol-cwcom
   - Widely deployed, simple timing-based encoding

2. **MOPP** (Morse Over Packet Protocol)
   - https://github.com/oe1wkl/Morserino-32
   - Bandwidth-optimized for LoRa/RF links

3. **DL4YHF Remote CW Keyer Protocol**
   - https://www.qsl.net/dl4yhf/Remote_CW_Keyer/
   - Production-tested, comprehensive Windows implementation

4. **Vail Adapter**
   - https://github.com/Vail-CW/vail-adapter
   - Modern USB HID approach with web browser compatibility

### 8.2 Technical Standards

- **IETF RFC 3550**: RTP (Real-time Transport Protocol)
- **IETF RFC 5246**: TLS for secure control channel
- **IETF RFC 5389**: STUN for NAT traversal
- **ITU-T G.711**: A-law/μ-law audio compression
- **IETF RFC 6716**: Opus audio codec

### 8.3 Amateur Radio Standards

- **IARU Region 1**: Band plans and operating practices
- **FCC Part 97**: US amateur radio regulations (remote control)
- **Icom CI-V**: Radio control protocol documentation
- **Yaesu CAT**: Radio control protocol

### 8.4 Morse Code Resources

- **ARRL**: Morse code timing standards
- **CWOPS**: High-speed CW best practices
- **SKCC**: Straight key timing characteristics

---

## Appendix A: Example Configuration Files

### A.1 Client Configuration (YAML)
```yaml
# cw-client.yaml
client:
  call_sign: "N0CALL"
  server_url: "cw.example.com"
  server_port: 7355
  
keyer:
  type: "iambic_b"  # straight, bug, iambic_a, iambic_b
  speed_wpm: 20
  weight: 50  # 30-70, affects dash/space ratio
  
hardware:
  key_interface: "serial"  # serial, gpio, usb
  serial_port: "/dev/ttyUSB0"
  pin_dit: 8  # CTS
  pin_dah: 6  # DSR
  
sidetone:
  # TX Sidetone (your own keying)
  tx:
    enabled: true
    method: "serial_txd"  # audio, serial_txd, external
    frequency: 600  # Hz
    volume: 80  # 0-100
    rise_time_ms: 5
    fall_time_ms: 5
    
  # RX Sidetone (peer/remote keying)
  rx:
    enabled: true
    frequency: 700  # Different from TX for distinction
    volume: 70  # Slightly quieter than TX
    jitter_buffer_ms: 100
    
    # Visual indicators
    show_waveform: true
    show_decoder_output: true
    
  # Audio mixing
  mix_mode: "stereo"  # stereo, mono, separate
  tx_channel: "left"   # If stereo
  rx_channel: "right"  # If stereo
  
audio:
  output_device: "default"
  latency_ms: 20
  sample_rate: 48000
  
network:
  protocol: "hybrid"  # cwcom, dl4yhf, hybrid
  udp_port: 7355
  tcp_port: 7356
  use_qos: true
  jitter_buffer_ms: 100
```

### A.2 Server Configuration
```yaml
# cw-server.yaml
server:
  call_sign: "W1AW"
  listen_address: "0.0.0.0"
  listen_port: 7355
  max_clients: 5
  
radio:
  type: "icom_ic7300"  # icom_*, yaesu_*, kenwood_*, gpio
  control_method: "civ"  # civ, cat, gpio, hamlib
  serial_port: "/dev/ttyUSB1"
  civ_address: 0x94
  
  keying:
    output_pin: 4  # DTR
    ptt_pin: 7     # RTS
    
  audio:
    input_device: "USB Audio CODEC"
    sample_rate: 8000
    
access_control:
  require_auth: true
  allowed_users:
    - call: "N0CALL"
      permissions: ["transmit", "control", "instructor"]
    - call: "N1CALL"  
      permissions: ["receive", "training"]
      
training_mode:
  enabled: true
  disable_radio_output: true  # Safety: no actual TX in training
  
  relay:
    mode: "selective"  # all_to_all, instructor_only, selective
    max_students: 10
    
  features:
    cw_decode: true
    timing_analysis: true
    record_sessions: true
    session_timeout_minutes: 60
    
  sidetone_relay:
    enabled: true
    preserve_timing: true  # Use jitter buffer
    
  feedback:
    auto_score: true
    timing_threshold_ms: 10  # ±10ms = acceptable
    accuracy_goal: 95  # percent
      
security:
  use_tls: true
  cert_file: "/etc/cw/server.crt"
  key_file: "/etc/cw/server.key"
```

---

## Appendix B: Bandwidth Analysis

### B.1 Typical Traffic Rates

**CW Keying** (20 WPM, average word length 5 chars):
- Characters per minute: 20 * 5 = 100
- Elements per minute: ~350 (avg 3.5 elements/char)
- State changes per minute: ~700 (key up + key down)
- Bytes per minute: 700 * 1 byte = 700 bytes
- **Bitrate: ~100 bps** ✅ Extremely efficient

**Audio Streaming** (μ-law, 8 kHz):
- Sample rate: 8000 samples/sec
- Bits per sample: 8
- **Bitrate: 64 kbps**

**Control Messages**:
- Heartbeat: 10 bytes/sec = 80 bps
- Frequency changes: Infrequent, <100 bps average

**Total Bandwidth**:
- CW only: ~100 bps ✅ LoRa compatible
- CW + Audio: ~65 kbps (adequate for most internet connections)

### B.2 Comparison with Other Modes

| Mode | Bandwidth | Latency | Fidelity |
|------|-----------|---------|----------|
| CW (our protocol) | 100 bps | 50-100ms | Perfect |
| Phone (Opus 12kbps) | 12 kbps | 40-60ms | Good |
| Digital (FT8) | 50 Hz | 15s | N/A |
| SSTV | 3 kHz | Minutes | N/A |

---

## Appendix C: Security Considerations

### C.1 Threats

1. **Eavesdropping**: Plaintext CW packets reveal communications
2. **Replay attacks**: Captured packets resent to cause interference
3. **Man-in-the-middle**: Attacker intercepts and modifies packets
4. **Denial of service**: Flood server with invalid packets
5. **Unauthorized access**: Non-licensed operators keying transmitter

### C.2 Mitigations

**Authentication**:
```
- Require callsign + password for TX permission
- Optional client certificates for strong identity
- Token-based session management
```

**Encryption**:
```
- TLS 1.3 for control channel (TCP)
- DTLS for CW/audio channels (UDP) if latency permits
- Pre-shared keys for low-overhead option
```

**Rate Limiting**:
```c++
// Prevent packet flood DoS
class RateLimiter {
    static const int MAX_PACKETS_PER_SECOND = 1000;
    std::unordered_map<IPAddress, int> clientCounts;
    
    bool allow(IPAddress client) {
        int count = clientCounts[client]++;
        if (count > MAX_PACKETS_PER_SECOND) {
            logWarning("Rate limit exceeded for " + client.toString());
            return false;
        }
        return true;
    }
};
```

**Legal Compliance**:
```
- Log all transmissions with callsign + timestamp
- Enforce PTT timeouts (e.g., 10 minutes max)
- Implement emergency shutoff capability
- Display mandatory station identification
```

---

## Appendix D: Frequency Spectrum Considerations

### D.1 CW Bandwidth Requirements

**Ideal CW signal**: 
- Rise/fall time: 5-10ms (prevent key clicks)
- Effective bandwidth: ~150 Hz @ 20 WPM

**Formula**:
```
BW = 1.2 * (speed_wpm / 1.2)  
   = speed_wpm Hz

At 20 WPM: ~20 Hz for perfect sine envelope
At 50 WPM: ~50 Hz (HSCW)
```

**Practical considerations**:
- Add 100 Hz margin for drift/stability
- Total filter bandwidth: 150-200 Hz

### D.2 Audio Quality Requirements

**For CW reception**:
- Bandwidth: 300-3000 Hz (sufficient for copy)
- Sample rate: 8 kHz (Nyquist satisfied)
- Dynamic range: 12-bit minimum (72 dB)

**Codec comparison**:
- μ-law/A-law: 64 kbps, adequate for CW
- Opus: 6-12 kbps, better quality
- MP3: Avoid (patents + latency)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-11-24 | [Your Name] | Initial specification |

---

## License

This specification is released under the [Creative Commons CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) license.

You are free to:
- **Share** — copy and redistribute the material
- **Adapt** — remix, transform, and build upon the material

Under the following terms:
- **Attribution** — You must give appropriate credit
- **ShareAlike** — Distribute derivatives under the same license

---

**Document Status**: Draft for Review
**Target Audience**: Software developers, radio control engineers, ham radio operators
**Related Documents**: Implementation guide, API reference, hardware interface spec
