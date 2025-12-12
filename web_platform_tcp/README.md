# CW Studio - TCP Timestamp Protocol Web Platform

Multi-user web-based Morse code practice platform using TCP Timestamp protocol for burst-resistant timing.

**Live Demo:** TBD (Deploy to Cloudflare Pages)

## Features

✅ **TCP Timestamp Protocol** - Burst-resistant timing perfect for WiFi/Internet  
✅ **Multi-user Rooms** - Practice with multiple operators in named rooms  
✅ **Real-time CW Decoder** - Automatic Morse code to text conversion  
⚠️ **Cloudflare Workers** - Echo mode only (multi-user requires Durable Objects $5/mo)  
✅ **WebSocket Relay** - Low-latency event distribution  
✅ **No Installation** - Works in any modern browser  
⚠️ **Free Tier Hosting** - Single-user testing only (multi-user needs paid plan or VPS)

**Status:** Frontend complete, multi-user relay blocked by Cloudflare free tier limitation.  

## Architecture Overview

**Simple Browser-to-Browser Relay (Pass-Through)**

```
┌──────────────────┐                    ┌──────────────────┐
│  Browser Alice   │                    │  Browser Bob     │
│  (SM5ABC)        │                    │  (W1ABC)         │
├──────────────────┤                    ├──────────────────┤
│ • Keyboard: Z/X  │                    │ • Receives events│
│ • Text-to-CW     │                    │ • Jitter buffer  │
│ • Paddle to CW
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

## Why TCP Timestamp Protocol?

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

## Use Cases

### 1. Multi-User Practice Rooms
```
Room: "main"
  └─ SM5ABC (25 WPM)
  └─ W1ABC (20 WPM)
  └─ G0XYZ (30 WPM)

Each user sends CW independently
All users hear everyone's CW with decoder
The sender shall only hear its own sidetone from client (not from browser due to delay!)
```

### 2. Training Sessions
```
Room: "training-15wpm"
  └─ Instructor (sends practice text)
  └─ 5-10 students (receive and decode)
  └─ Students can also practice
```

### 3. Contest Simulation
```
Room: "contest"
  └─ Multiple stations sending rapid exchanges
  └─ Test pileup handling and speed copying
```

## Project Structure

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

## Technical Design

### Protocol Layer (TCP Timestamp)

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

## Protocol Design

**WebSocket JSON Events (Browser-to-Browser)**

This platform uses **pure WebSocket JSON messaging** between browsers. The "TCP-TS" name refers to the timing principles (timestamps for burst-resistance), not binary TCP protocol.

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

**Why JSON over WebSocket (not binary TCP-TS)?**
- ✅ Browsers speak WebSocket natively
- ✅ Cloudflare Workers handle WebSocket
- ✅ Human-readable for debugging
- ✅ Same format browser → worker → browser (pass-through)
- ✅ Timestamp principles still apply (burst-resistant)

**Relationship to test_implementation:**
- Uses same **timing principles** (timestamps, jitter buffer)
- Different **transport** (WebSocket vs raw TCP)
- Browser version = web-friendly implementation of same concepts

## Browser Requirements

- ✅ Chrome/Edge 56+
- ✅ Firefox 52+
- ✅ Safari 11+
- ✅ Mobile browsers (iOS Safari, Chrome Android)

**Required APIs:**
- WebSocket (event communication)
- Web Audio API (sidetone generation)
- Keyboard events (manual keying)

## Performance Characteristics

**Bandwidth per user:**
- Sending 25 WPM: ~10 events/sec = 500 bytes/sec
- Receiving 3 users: ~1500 bytes/sec
- **Total: ~2 KB/sec** (vs 40 KB/sec for WebRTC audio)

**Latency:**
- WebSocket relay: ~20-50ms
- Jitter buffer: 100-500ms (configurable)
- Audio scheduling: <1ms precision
- **Total: 120-200ms** (consistent, predictable)

**CPU usage:**
- Web Audio API: ~2-5%
- Decoder: ~1-2%
- WebSocket: <1%
- **Total: <10% per room**

## Deployment

### ⚠️ Cloudflare Workers Limitation (Multi-User)

**Critical Issue Discovered:** Cloudflare Workers free tier **cannot relay WebSocket messages** between multiple users.

**Error:** `Cannot perform I/O on behalf of a different request`

**Root Cause:**
- WebSocket objects are bound to the request that created them
- Cannot store WebSocket objects globally for broadcast
- Workers free tier does not allow storing I/O objects across requests

**Solutions:**

1. **Cloudflare Durable Objects** ($5/month)
   - Stateful WebSocket storage
   - Proper multi-user support
   - Global deployment
   - [See Documentation](https://developers.cloudflare.com/durable-objects/)

2. **Node.js + Socket.IO** (VPS or local)
   - Simple relay server (~30 min implementation)
   - Full control over WebSocket handling
   - Perfect for European users (Frankfurt VPS = ~20ms)
   - See `PLATFORM_COMPARISON.md` for details

3. **Current Echo Mode** (Testing only)
   - Worker echoes events back to sender
   - Good for testing protocol
   - Not suitable for multi-user

**Recommendation:**
- **Python client users** (cw_studio_client_with_sidetone.py): Node.js server
- **Web browser users**: Cloudflare Durable Objects or Node.js
- **Single region** (Europe): Node.js VPS
- **Global users**: Cloudflare Durable Objects

### Cloudflare Pages (Frontend)
```bash
cd public
wrangler pages deploy . --project-name=cw-studio-tcp
# URL: https://cw-studio-tcp.pages.dev
```

### Cloudflare Worker (Relay) - ⚠️ Echo Mode Only
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

## Development Roadmap

### Phase 1: Core Functionality (MVP)
- [x] Project structure
- [x] Cloudflare Worker relay (echo mode - **multi-user blocked by free tier limitation**)
- [x] Frontend landing page
- [x] Room interface with manual keying
- [x] TCP-TS client (WebSocket)
- [x] Jitter buffer (timestamp-based)
- [x] Audio sidetone (Web Audio API)
- [x] Basic CW decoder
- [ ] **Multi-user relay** (needs Durable Objects or Node.js)

### Phase 2: Enhanced Features
- [ ] Text-to-CW automated sending
- [ ] WPM estimation and display
- [ ] User list in room
- [ ] Volume control per user
- [ ] Frequency selection per user
- [ ] Statistics (packets sent/received)

### Phase 3: Advanced Features
- [ ] Recording/playback of sessions
- [ ] Practice drills library
- [ ] QSO templates (CQ, contest exchange)
- [ ] Mobile-optimized interface
- [ ] Local Python receiver compatibility

## Comparison with WebRTC Version

| Feature | WebRTC Audio | TCP-TS Events |
|---------|--------------|---------------|
| Bandwidth | 40 KB/s | 2 KB/s |
| Latency | 70-140ms | 120-200ms |
| Timing Precision | ±50ms | ±1ms |
| Burst Resistance | ❌ | ✅ |
| Decoder Accuracy | Medium | High |
| CPU Usage | Medium | Low |
| Scalability | Mesh (2-8) | Relay (100+) |
| Protocol | WebRTC | TCP-TS |

**Verdict:** TCP-TS is better for CW practice due to precise timing and scalability.

## Contributing

1. Fork repository
2. Create feature branch
3. Test locally with `wrangler dev`
4. Submit pull request

## License

MIT License - see main repository LICENSE file

## Credits

- **Author:** Tomas (SM0ONR)
- **Project:** Duration-Encoded CW Protocol
- **Protocol:** TCP Timestamp (burst-resistant)
- **Repository:** https://github.com/tompatulpan/duration-encoded-cw-protocol

## Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed system design
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment instructions
- [PLATFORM_COMPARISON.md](PLATFORM_COMPARISON.md) - Cloudflare vs Node.js comparison
- [TESTING.md](TESTING.md) - Testing procedures and results
- [../test_implementation/](../test_implementation/) - Python protocol implementation
- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/) - Required for multi-user
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)

## Known Limitations

### Multi-User WebSocket Relay

**Issue:** Cloudflare Workers free tier cannot relay WebSocket messages between users.

**Symptoms:**
```
Error: Cannot perform I/O on behalf of a different request.
I/O objects (such as streams, request/response bodies, and others) 
created in the context of one request handler cannot be accessed 
from a different request's handler.
```

**Impact:**
- ✅ Single user can connect and send events (echo mode works)
- ❌ Cannot broadcast to other users in same room
- ❌ Multi-user practice rooms non-functional on free tier

**Workarounds:**
1. **Upgrade to Durable Objects** ($5/month) - Recommended for web users
2. **Deploy Node.js relay server** (VPS or local) - Recommended for Python clients
3. **Use Python clients directly** (test_implementation/cw_studio_client_with_sidetone.py)

See `PLATFORM_COMPARISON.md` for detailed analysis of solutions.

---

**73 de SM0ONR** 📻
