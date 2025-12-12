# Quick Test Guide

## ✅ Both servers are running!

### Worker (WebSocket Relay)
- URL: http://localhost:8787
- WebSocket: ws://localhost:8787
- Status: Running

### Frontend (Web Server)
- URL: http://localhost:8000
- Landing Page: http://localhost:8000/index.html
- Room: http://localhost:8000/room.html?room=main&callsign=TEST1
- Status: Running

## How to Test

### Single User Test
1. Open browser: http://localhost:8000/index.html
2. Enter callsign (e.g., TEST1)
3. Click "Join Room"
4. Try keying: Press Z (dit) or X (dah)
5. Try text: Enter "CQ CQ" and click "Send Text"

### Multi-User Test
1. Open first browser tab:
   - http://localhost:8000/room.html?room=main&callsign=SM0ONR
2. Open second browser tab (or another browser):
   - http://localhost:8000/room.html?room=main&callsign=W1ABC
3. Key in one tab - you should hear and see decoded text in both tabs!

### What to Expect
✅ **Paddle keying:** Press Z/X keys to send dits/dahs
✅ **Local sidetone:** Hear your own CW immediately
✅ **Remote playback:** Other users hear your CW after buffer delay (150ms)
✅ **Decoder:** See decoded Morse text from all users
✅ **Statistics:** Watch events sent/received counters

### Troubleshooting

**No audio?**
- Click anywhere on page first (browser audio policy)
- Check "Audio Enabled" checkbox in settings
- Adjust volume slider

**Connection failed?**
- Check worker is running: http://localhost:8787/health (should show "OK")
- Check browser console (F12) for errors
- Verify WebSocket URL is `ws://localhost:8787` (not wss://)

**CW not sending?**
- Check connection status shows "Connected" (green)
- Try pressing Z or X keys
- Check statistics panel shows events sent

## Deploy to Cloudflare

When ready to deploy:

```bash
# Deploy worker
cd worker
npx wrangler login
npx wrangler deploy

# Note the URL (e.g., https://cw-studio-relay.your-subdomain.workers.dev)

# Update frontend URLs in:
# - public/js/landing.js
# - public/js/room-controller.js

# Deploy frontend
cd ..
npx wrangler pages deploy public/ --project-name=cw-studio-tcp
```

## Testing Checklist

- [ ] Landing page loads
- [ ] Can join room with callsign
- [ ] Connection status shows "Connected"
- [ ] Can send dits (Z key)
- [ ] Can send dahs (X key)
- [ ] Hear local sidetone immediately
- [ ] Can send text ("CQ CQ")
- [ ] Decoder shows your text
- [ ] Two tabs can communicate
- [ ] Other user's CW appears in decoder
- [ ] Statistics update (events sent/received)
- [ ] Buffer settings work
- [ ] Volume slider works
- [ ] Frequency slider works

## Architecture Verification

Check that data flows correctly:

1. **Press Z key** →
2. Browser captures keydown →
3. Sends JSON to worker: `{type:'cw_event', key_down:true, duration_ms:48, ...}` →
4. Worker broadcasts to room members →
5. Other browsers receive event →
6. Jitter buffer schedules playout →
7. Audio plays at correct time →
8. Decoder processes event →
9. Text appears on screen

**All using WebSocket JSON pass-through - no protocol translation!**

73! 📻
