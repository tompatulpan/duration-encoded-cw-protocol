# TCP Timestamp Protocol - Web Platform

## Overview

This directory contains a web-based implementation of the TCP Timestamp Protocol for Morse code transmission over WebSocket connections.

**Status:** Protocol documentation and design complete. Web platform implementation details available in separate section below.

## Core Protocol Design

## Core Protocol Design

### TCP Timestamp Protocol Overview

**TCP Timestamp Protocol Advantages:**
- ✅ **Events, not audio**: Send key state + duration + timestamp
- ✅ **Absolute timing**: Each event has precise playout time
- ✅ **Burst-resistant**: WiFi/TCP bursts don't affect timing
- ✅ **Low bandwidth**: ~50 bytes/event vs ~5KB/sec audio
- ✅ **Perfect timing**: ±1ms accuracy (vs ±50ms for audio)
- ✅ **Decoder-friendly**: Precise timing = better decoding

**Event Format:**
```javascript
{
  type: 'cw_event',
  callsign: 'SM5ABC',
  key_down: true,          // true=DOWN, false=UP
  duration_ms: 48,         // How long key was in this state
  timestamp_ms: 1234,      // When event occurred (ms since session start)
  sequence: 42             // Packet sequence number
}
```

### Protocol Design Principles

### Protocol Design Principles

**WebSocket JSON Events**

This platform uses **pure WebSocket JSON messaging**. The "TCP-TS" name refers to the timing principles (timestamps for burst-resistance), not binary TCP protocol.

**Event format:**
```javascript
{
  type: 'cw_event',
  callsign: 'SM5ABC',
  key_down: true,
  duration_ms: 48,
  timestamp_ms: 1234,
  sequence: 42
}
```

**Why JSON over WebSocket?**
- ✅ Browsers speak WebSocket natively
- ✅ Human-readable for debugging
- ✅ Self-contained packets (no state tracking)
- ✅ Timestamp principles still apply (burst-resistant)

**Relationship to test_implementation:**
- Uses same **timing principles** (timestamps, jitter buffer)
- Different **transport** (WebSocket vs raw TCP)

### Why Keep Both Duration AND Timestamp?

The protocol includes **both** `duration_ms` and `timestamp_ms` fields, even though duration could theoretically be calculated from timestamp differences. This is intentional:

**Reasons to keep both fields:**

1. **Self-contained packets** - Each event is independently understandable
2. **Decoder friendliness** - Direct access to duration for dit/dah classification
3. **First packet handling** - No special case (first packet has explicit duration)
4. **Debugging ease** - Both values visible without calculation
5. **Bandwidth negligible** - Extra 1-2 bytes = 20 bytes/sec (~0.0025% of WiFi)
6. **Protocol clarity** - Clear semantic meaning (state + duration + when)
7. **UDP compatibility** - Similar structure to UDP-FEC variant (packet loss safe)
8. **Stateless processing** - No need to track previous timestamps

**Calculated duration approach (NOT used):**
```javascript
// Would require state tracking
duration = currentTimestamp - previousTimestamp;
// Problems: First packet? What if out-of-order? More complex.
```

**Explicit duration approach (current):**
```javascript
// Self-contained, works immediately
const isDit = (event.duration_ms < 80);  // Direct classification
// No state, no edge cases, simple.
```

**Bandwidth comparison:**
- Current: ~50 bytes per event
- Without duration: ~48 bytes per event  
- Savings: 2 bytes = **0.16 Kbps per user** (negligible)

The engineering simplicity and robustness justify the minimal bandwidth cost.

---

## Web Platform Implementation (Browser-Based)

⚠️ **Note:** The following sections describe a browser-based implementation of the TCP-TS protocol. This is experimental and currently has limitations with multi-user support on free hosting tiers.

### Features

✅ **TCP Timestamp Protocol** - Burst-resistant timing perfect for WiFi/Internet  
✅ **Multi-user Rooms** - Practice with multiple operators in named rooms  
✅ **Real-time CW Decoder** - Automatic Morse code to text conversion  
⚠️ **Cloudflare Workers** - Echo mode only (multi-user requires Durable Objects $5/mo)  
✅ **WebSocket Relay** - Low-latency event distribution  
✅ **No Installation** - Works in any modern browser  
⚠️ **Free Tier Hosting** - Single-user testing only (multi-user needs paid plan or VPS)

**Status:** Frontend complete, multi-user relay blocked by Cloudflare free tier limitation.

### Architecture

**Simple Browser-to-Browser Relay (Pass-Through)**

```
┌──────────────────┐                    ┌──────────────────┐
│  Browser Alice   │                    │  Browser Bob     │
│  (SM5ABC)        │                    │  (W1ABC)         │
├──────────────────┤                    ├──────────────────┤
│ • Keyboard: Z/X  │                    │ • Receives events│
│ • Text-to-CW     │                    │ • Jitter buffer  │
│ • Paddle to CW   │                    │                  │
│ • Generate events│                    │ • Sidetone plays │
│ • TX sidetone    │                    │ • Decoder shows  │
└────────┬─────────┘                    └────────▲─────────┘
         │                                       │
         │ WebSocket                             │ WebSocket
         │ JSON events                           │ JSON events
         └───────────────┐         ┌─────────────┘
                         │         │
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

**Key Design: Same JSON format both directions**
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
The sender shall only hear its own sidetone from client (not from browser due to delay!)
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
│   │
│   ├── css/
│   │   └── styles.css           # All styling
│   │
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

### Browser-Specific Technical Implementation

<!--

#### Protocol Layer (TCP Timestamp)

**Packet Structure (WebSocket JSON):**
```javascript
{
  type: 'cw_event',
  callsign: 'SM5ABC',
  key_down: true,
  duration_ms: 48,
  timestamp_ms: 1234,     // Relative to sender's session start
  sequence: 42
}
```

**Why TCP-style timestamps over WebSocket?**
- WebSocket is already TCP-based (reliable, ordered)
- Timestamps provide absolute timing reference
- Immune to network bursts (WiFi, cellular)
- Compatible with existing test_implementation/cw_receiver_tcp_ts.py

### Jitter Buffer (Client-side)

**Two-stage processing:**

1. **Reception (WebSocket):**
   ```javascript
   // Events arrive from network
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

// Room-based broadcast
function broadcastToRoom(roomId, event, senderWs) {
  rooms[roomId].forEach(user => {
    if (user.ws !== senderWs) {
      user.ws.send(JSON.stringify(event));  // Same JSON format
    }
  });
}
```

**No translation, just relay:**
- ✅ Receives JSON from browser
- ✅ Broadcasts same JSON to other browsers
- ✅ No protocol conversion
- ✅ No audio processing
- ✅ ~50 bytes per event
- ✅ Scales easily on Cloudflare free tier

-->

-->

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

<!--

#<!--

#### Cloudflare Pages (Frontend)
```bash
cd public
wrangler pages deploy . --project-name=cw-studio-tcp
# URL: https://cw-studio-tcp.pages.dev
```

#### Cloudflare Worker (Relay) - ⚠️ Echo Mode Only
```bash
cd worker
npm install
wrangler deploy
# URL: wss://cw-relay.your-subdomain.workers.dev
# NOTE: Only works for single-user testing (echo mode)
```

**Cost:**
- Free tier: Echo mode only (single user)
- Durable Objects: $5/month (multi-user)
- Node.js VPS: $5-10/month (alternative)

-->

---

## Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed system design
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment instructions  
- [PLATFORM_COMPARISON.md](PLATFORM_COMPARISON.md) - Cloudflare vs Node.js comparison
- [TESTING.md](TESTING.md) - Testing procedures and results
- [../test_implementation/](../test_implementation/) - Python protocol implementation

## Related Documentation

- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/)
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)

## Known Limitations

⚠️ **Multi-User WebSocket Relay:** Cloudflare Workers free tier cannot relay WebSocket messages between users. Requires Durable Objects ($5/mo) or Node.js server. See PLATFORM_COMPARISON.md for details.

---

**73 de SM0ONR** 📻
