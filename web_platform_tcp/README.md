**Status:** 🚧 In development - Features and structure subject to change

# TCP Timestamp Protocol - Web Platform

## Overview

This directory contains a **browser-based implementation** of the DECW protocol using WebSocket connections and JSON event messaging.

The web platform uses the same timing principles as the TCP timestamp protocol (burst-resistant absolute timing) but adapted for browser environments using WebSocket instead of raw TCP.

**Status:** Protocol design complete. Multi-user relay requires paid hosting or self-hosted VPS.

---

## Protocol Design

### WebSocket JSON Events

This platform uses **WebSocket with JSON messaging** (not binary TCP). The "TCP-TS" name refers to the timing principles (timestamps for burst-resistance), not the transport.

**Event format:**
```javascript
{
  type: 'cw_event',
  callsign: 'SM5ABC',
  key_down: true,          // true=DOWN, false=UP
  duration_ms: 48,         // How long key was in PREVIOUS state
  timestamp_ms: 1234,      // When transition occurred (ms since session start)
  sequence: 42             // Packet sequence number
}
```

### Key Design Principles

**Why WebSocket over raw TCP?**
- ✅ Browsers speak WebSocket natively
- ✅ Human-readable JSON for debugging
- ✅ Self-contained packets (no state tracking)
- ✅ Same timestamp principles apply (burst-resistant)

**Relationship to test_implementation:**
- Uses same **timing principles** (timestamps, jitter buffer)
- Different **transport** (WebSocket vs raw TCP)
- Same **scheduling algorithm** (absolute time reference)

### Why Keep Both Duration AND Timestamp?

The protocol includes **both** `duration_ms` and `timestamp_ms` fields for several reasons:

1. **Self-contained packets** - Each event is independently understandable
2. **Decoder friendliness** - Direct access to duration for dit/dah classification
3. **First packet handling** - No special case (first packet has explicit duration)
4. **Debugging ease** - Both values visible without calculation
5. **Bandwidth negligible** - Extra 1-2 bytes = ~0.16 Kbps per user (0.0025% of WiFi)
6. **Protocol clarity** - Clear semantic meaning (state + duration + when)
7. **Stateless processing** - No need to track previous timestamps

**Bandwidth comparison:**
- Current: ~50 bytes per event
- Without duration: ~48 bytes per event  
- Savings: 2 bytes = negligible (~0.16 Kbps)

The engineering simplicity justifies the minimal bandwidth cost.

**Protocol Advantages:**
- ✅ **Events, not audio**: Send key state + timing (not audio samples)
- ✅ **Absolute timing**: Each event has precise playout time
- ✅ **Burst-resistant**: WiFi/TCP bursts don't affect timing
- ✅ **Low bandwidth**: ~50 bytes/event vs ~5KB/sec for audio
- ✅ **Perfect timing**: ±1ms accuracy (vs ±50ms for audio)
- ✅ **Decoder-friendly**: Precise timing = better decoding

---

## Web Platform Implementation

This is an **experimental browser-based implementation**. Multi-user support currently limited by free hosting tier.

### Features

✅ **Burst-resistant timing** - TCP timestamp protocol adapted for WebSocket  
✅ **Multi-user rooms** - Practice with multiple operators in named rooms  
✅ **Real-time CW decoder** - Automatic Morse code to text conversion  
⚠️ **Cloudflare Workers** - Echo mode only (multi-user requires Durable Objects $5/mo)  
✅ **WebSocket relay** - Low-latency event distribution  
✅ **No installation** - Works in any modern browser  
⚠️ **Free tier limitation** - Single-user testing only (multi-user needs paid plan or VPS)

### Architecture

**Browser-to-Browser Relay (Pass-Through)**

```
┌──────────────────┐                    ┌──────────────────┐
│  Browser Alice   │                    │  Browser Bob     │
│  (SM5ABC)        │                    │  (W1ABC)         │
├──────────────────┤                    ├──────────────────┤
│ • Keyboard: Z/X  │                    │ • Receives events│
│ • Text-to-CW     │                    │ • Jitter buffer  │
│ • Paddle to CW   │                    │ • Sidetone plays │
│ • Generate events│                    │ • Decoder shows  │
│ • TX sidetone    │                    │                  │
└────────┬─────────┘                    └────────▲─────────┘
         │                                       │
         │ WebSocket JSON                        │ WebSocket JSON
         └───────────────┐         ┌─────────────┘
                         ↓         ↓
                ┌────────────────────────┐
                │  Cloudflare Worker     │
                │  (Simple Relay)        │
                ├────────────────────────┤
                │ • Room management      │
                │ • Pass-through events  │
                │ • Broadcast to room    │
                │ • User presence        │
                │ • NO translation       │
                │ • NO audio processing  │
                └────────────────────────┘
```

**Key Design:**
- Browser → Worker: `{type: 'cw_event', callsign, key_down, duration_ms, timestamp_ms}`
- Worker → Browsers: Same format (just pass through and broadcast)
- No protocol translation needed
- Pure JavaScript/WebSocket architecture

### Use Cases

#### 1. Multi-User Practice Rooms
```
Room: "main"
  └─ SM5ABC (25 WPM)
  └─ W1ABC (20 WPM)
  └─ G0XYZ (30 WPM)

Each user sends CW independently
All users hear everyone's CW with decoder
Sender hears only own TX sidetone (no delay)
```

#### 2. Training Sessions
```
Room: "training-15wpm"
  └─ Instructor (sends practice text)
  └─ 5-10 students (receive and decode)
  └─ Students can also practice
```

#### 3. Contest Simulation
```
Room: "contest"
  └─ Multiple stations sending rapid exchanges
  └─ Test pileup handling and speed copying
```

### Project Structure

```
web_platform_tcp/
├── README.md                    # This file
├── ARCHITECTURE.md              # Detailed technical architecture
├── DEPLOYMENT.md                # Deployment guide
│
├── public/                      # Static frontend (Cloudflare Pages)
│   ├── index.html               # Landing page (room selection)
│   ├── room.html                # Practice room interface
│   ├── css/
│   │   └── styles.css           # All styling
│   └── js/
│       ├── landing.js           # Landing page logic
│       ├── room-controller.js   # Main room application
│       ├── tcp-ts-client.js     # TCP-TS protocol (WebSocket)
│       ├── cw-decoder.js        # Morse decoder
│       ├── audio-handler.js     # Web Audio API (sidetone)
│       └── jitter-buffer.js     # Timestamp-based scheduling
│
└── worker/                      # Cloudflare Worker (WebSocket relay)
    ├── src/
    │   └── index.js             # WebSocket relay server
    ├── wrangler.toml            # Worker configuration
    └── package.json             # Dependencies
```

### Browser Requirements

- ✅ Chrome/Edge 56+
- ✅ Firefox 52+
- ✅ Safari 11+
- ✅ Mobile browsers (iOS Safari, Chrome Android)

**Required APIs:**
- WebSocket (event communication)
- Web Audio API (sidetone generation)
- Keyboard events (manual keying)

### Deployment

**⚠️ Current Limitation:**

Cloudflare Workers free tier cannot relay WebSocket messages between users. Options:

1. **Cloudflare Durable Objects** - $5/month (enables multi-user)
2. **Node.js VPS** - $5-10/month (self-hosted alternative)
3. **Echo mode** - Free tier works for single-user testing only

See [DEPLOYMENT.md](DEPLOYMENT.md) and [PLATFORM_COMPARISON.md](PLATFORM_COMPARISON.md) for details.

---

## Technical Implementation Details

### Jitter Buffer (Client-side)

**Two-stage processing:**

1. **Reception (WebSocket):**
   ```javascript
   ws.onmessage = (msg) => {
     const event = JSON.parse(msg.data);
     jitterBuffer.addEvent(event);
   }
   ```

2. **Scheduling (Absolute time):**
   ```javascript
   // Calculate playout time from timestamp
   playoutTime = senderTimelineOffset + (timestamp_ms / 1000.0) + bufferMs;
   
   // Schedule audio precisely
   scheduleAt(playoutTime, () => {
     sidetone.setKey(event.key_down);
     decoder.processEvent(event);
   });
   ```

**Buffer sizing:**
- LAN: 50ms (minimal delay)
- WiFi: 100-150ms (burst protection)
- Internet: 150-500ms (jitter tolerance)

### Audio Generation (Web Audio API)

**Sidetone per user:**
```javascript
// Create oscillator for each active callsign
oscillators['SM5ABC'] = audioContext.createOscillator();
oscillators['SM5ABC'].frequency.value = 700;  // Hz

// Key down/up with envelope
gainNode.gain.setTargetAtTime(
  event.key_down ? 0.3 : 0.0,
  playoutTime,
  0.004  // 4ms attack/decay
);
```

**Why not shared oscillator?**
- Each user needs independent frequency (multi-user identification)
- Overlapping CW from multiple operators
- Individual volume control

### CW Decoder (JavaScript)

**Timing-based classification:**
```javascript
// Measure key-down duration
const duration = event.duration_ms;

// Classify as dit or dah
if (duration < threshold) {
  symbol = '.';  // Dit
} else {
  symbol = '-';  // Dah
}

// Gap detection for character/word boundaries
if (gap > 200) {
  // Word space
} else if (gap > 100) {
  // Letter space - decode character
  const char = morseTable[buffer.join('')];
}
```

**Adaptive timing:**
- Estimates WPM from recent dits
- Adjusts thresholds dynamically
- Handles 10-40 WPM range

### Worker (Cloudflare)

**Simple pass-through relay:**
```javascript
// Receive event from browser
server.addEventListener('message', event => {
  const data = JSON.parse(event.data);
  
  // Pass through to all users in same room (except sender)
  if (data.type === 'cw_event') {
    broadcastToRoom(data.room, data, server);
  }
});
```

**No translation, just relay:**
- ✅ Receives JSON from browser
- ✅ Broadcasts same JSON to other browsers
- ✅ No protocol conversion
- ✅ ~50 bytes per event
- ✅ Scales easily (when paid tier used)

---

## Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed system design
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment instructions  
- [PLATFORM_COMPARISON.md](PLATFORM_COMPARISON.md) - Cloudflare vs Node.js comparison
- [TESTING.md](TESTING.md) - Testing procedures and results
- [../test_implementation/](../test_implementation/) - Python protocol implementation (TCP-TS reference)

## Related Documentation

- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/)
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)

---

**73 de SM0ONR** 📻

