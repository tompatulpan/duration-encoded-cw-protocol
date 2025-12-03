# CW Practice Web Platform

Real-time browser-based Morse code practice with multiple operators worldwide.

## Features

✅ **WebRTC P2P Audio** - Low latency (~70-100ms) peer-to-peer audio streaming  
✅ **Real-time CW Decoder** - Automatic Morse code to text conversion  
✅ **Mesh Networking** - Direct connections between 2-8 operators  
✅ **No Installation** - Works in any modern browser  
✅ **Free Hosting** - Runs on Cloudflare's free tier  
✅ **Open Source** - MIT licensed, fully customizable

## Architecture

```
Browser ←→ WebRTC P2P ←→ Browser
   ↓                       ↓
   └→ Signaling Server ←──┘
      (Cloudflare Worker)
```

- **Frontend:** Vanilla JavaScript, Web Audio API, WebRTC
- **Backend:** Cloudflare Workers (WebSocket signaling)
- **Hosting:** Cloudflare Pages (static assets)
- **Cost:** $0/month (free tier)

## Quick Start

### Local Development

1. **Start signaling server:**
   ```bash
   cd workers
   npm install -g wrangler
   wrangler dev
   ```

2. **Serve frontend:**
   ```bash
   cd public
   python3 -m http.server 8000
   ```

3. **Open browser:**
   ```
   http://localhost:8000/index.html
   ```

### Deploy to Production

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete deployment instructions.

Quick deploy:
```bash
# Deploy worker
cd workers && wrangler deploy

# Deploy pages
wrangler pages deploy public/ --project-name=cw-practice
```

## Project Structure

```
web_platform/
├── ARCHITECTURE.md          # Detailed architecture & scaling guide
├── DEPLOYMENT.md            # Step-by-step deployment instructions
├── README.md               # This file
│
├── public/                 # Static frontend files
│   ├── index.html          # Landing page
│   ├── room.html           # Practice room interface
│   │
│   ├── css/
│   │   └── styles.css      # All styling
│   │
│   └── js/
│       ├── landing.js      # Landing page logic
│       ├── room.js         # Room controller (main app logic)
│       ├── webrtc.js       # WebRTC mesh networking
│       ├── cw-decoder.js   # Morse decoder
│       └── audio.js        # Web Audio API handler
│
└── workers/                # Cloudflare Worker
    ├── signaling.js        # WebSocket signaling server
    └── wrangler.toml       # Worker configuration
```

## How It Works

### 1. User Joins Room
- Enters callsign and room name
- Browser requests microphone access
- Connects to signaling server via WebSocket

### 2. WebRTC Connection Establishment
- Signaling server exchanges SDP offers/answers
- ICE candidates negotiated for NAT traversal
- Direct P2P audio streams established

### 3. CW Detection & Decoding
- Audio input analyzed for tone presence
- Key-down duration classified as dit or dah
- Timing gaps detect character/word boundaries
- Morse pattern decoded to text

### 4. Display
- Decoded text shown for all operators
- Real-time WPM estimation
- Connection status indicators

## Browser Compatibility

- ✅ Chrome/Edge 56+
- ✅ Firefox 52+
- ✅ Safari 11+
- ✅ Mobile browsers (iOS Safari, Chrome Android)
- ❌ Internet Explorer (no WebRTC support)

## Scaling

**Current Implementation (Mesh):**
- Best for: 2-8 operators
- Bandwidth: ~40 kbps per peer connection
- Latency: 70-140ms

**Future Migration to SFU:**
- When: >8 operators needed
- Options: Cloudflare Calls ($0.05/GB) or self-hosted Janus (free)
- See [ARCHITECTURE.md](ARCHITECTURE.md) for details

## Development

### Testing Locally

```bash
# Terminal 1: Start worker
cd workers
wrangler dev

# Terminal 2: Serve frontend
cd public
python3 -m http.server 8000

# Terminal 3: Open browsers
open http://localhost:8000/index.html
# Open another browser window for second user
```

### Code Structure

**Room Controller (`room.js`):**
- Main application logic
- Ties together WebRTC, audio, and decoder
- Manages UI state

**WebRTC Client (`webrtc.js`):**
- Handles peer connections (mesh topology)
- SDP offer/answer negotiation
- ICE candidate exchange

**CW Decoder (`cw-decoder.js`):**
- JavaScript port of Python MorseDecoder
- Timing-based dit/dah classification
- WPM estimation

**Audio Handler (`audio.js`):**
- Web Audio API sidetone generation
- Microphone input analysis
- Tone detection for CW

**Signaling Server (`signaling.js`):**
- WebSocket server for peer discovery
- Relays SDP and ICE between peers
- Room management

## API

### Signaling Server WebSocket

**Client → Server:**
```javascript
{ type: 'join', roomId: 'main', callsign: 'SM0ONR' }
{ type: 'offer', to: 'peer123', offer: {...} }
{ type: 'answer', to: 'peer123', answer: {...} }
{ type: 'ice-candidate', to: 'peer123', candidate: {...} }
{ type: 'leave' }
```

**Server → Client:**
```javascript
{ type: 'joined', peerId: 'abc123', roomId: 'main' }
{ type: 'peer-list', peers: [{peerId, callsign}, ...] }
{ type: 'peer-joined', peerId: 'xyz789', callsign: 'W1ABC' }
{ type: 'peer-left', peerId: 'xyz789' }
{ type: 'offer', from: 'peer123', callsign: 'SM0ONR', offer: {...} }
{ type: 'answer', from: 'peer123', answer: {...} }
{ type: 'ice-candidate', from: 'peer123', candidate: {...} }
```

### REST API

**GET /api/rooms**
```json
{
  "rooms": [
    {"roomId": "main", "operatorCount": 3, "operators": ["SM0ONR", "W1ABC", "G0XYZ"]},
    {"roomId": "contest", "operatorCount": 5, "operators": [...]}
  ],
  "totalOperators": 8
}
```

## Troubleshooting

### WebSocket won't connect
- Check worker is deployed: `wrangler whoami`
- Verify URL in `room.js` matches worker URL
- Use `wss://` for HTTPS sites (not `ws://`)

### No audio between peers
- Check microphone permissions granted
- Verify firewall allows WebRTC (UDP)
- Try different browser (Chrome recommended)

### CW not decoding
- Check audio input level (not too quiet/loud)
- Use clean sine wave tone (500-700 Hz)
- Adjust threshold in `audio.js` if needed

### High latency
- Check network connection quality
- Verify STUN servers are accessible
- Consider geographic distance between operators

## Performance

**Bandwidth per operator:**
- Upload: ~40 kbps × (N-1) peers
- Download: ~40 kbps × (N-1) peers
- Example: 4 operators = 120 kbps up/down each

**Latency breakdown:**
- Audio encoding: ~20ms
- Network transit: ~30-100ms (varies by location)
- Audio decoding: ~20ms
- **Total: 70-140ms**

**Browser CPU usage:**
- Per peer connection: ~5-10%
- 3 peers = ~15-30% CPU

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

## License

MIT License - see [LICENSE](../LICENSE) file

## Credits

- **Author:** Tomas (SM0ONR)
- **Project:** Duration-Encoded CW Protocol
- **Repository:** https://github.com/tompatulpan/duration-encoded-cw-protocol

## Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed system architecture
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment instructions
- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [WebRTC Documentation](https://webrtc.org/)
- [Web Audio API Guide](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)

---

**73 de SM0ONR**
