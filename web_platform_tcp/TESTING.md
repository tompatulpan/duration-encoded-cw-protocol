# Quick Test Guide

## Starting Local Servers

### 1. Start Web Server (Frontend)
```bash
cd public
python3 -m http.server 8080 &
```

### 2. Start Worker (WebSocket Relay)
```bash
cd worker
npx wrangler dev &
```

### 3. Verify Both Running
```bash
curl http://localhost:8787/health  # Should show "OK"
curl http://localhost:8080/        # Should show HTML
```

## ✅ Server Status

### Worker (WebSocket Relay)
- URL: http://localhost:8787
- WebSocket: ws://localhost:8787
- Health: http://localhost:8787/health

### Frontend (Web Server)
- URL: http://localhost:8080
- Landing: http://localhost:8080/index.html
- Room: http://localhost:8080/room.html?room=main&callsign=TEST1

## How to Test

### Browser Test (Web Interface)

**1. Open browser:** http://localhost:8080

**2. Landing Page Test:**
   - Enter callsign (e.g., TEST1)
   - Enter room name (default: main)
   - Click "Join Room"

**3. Room Interface Test:**
   - **Keyboard keying:** Press Z (dit) or X (dah)
   - **Text-to-CW:** Enter "CQ CQ" and click "Send Text"
   - **Watch for:**
     - ✓ Local sidetone (immediate audio)
     - ✓ Echo events (should see them echoed back)
     - ✓ Decoder output (shows decoded text)
     - ✓ Statistics (events sent/received)

**4. Direct Room URL:**
```
http://localhost:8080/room.html?room=main&callsign=SM0ONR
```

### Python Client Test

**Run simulated client:**
```bash
python3 test_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign PYTHON_CLIENT \
  --wpm 25
```

**Expected output:**
```
Connecting to ws://localhost:8787...
✓ Connected as PYTHON_CLIENT

✓ Sending test pattern 'A A A' at 25 WPM
  Dit: 48ms, Dah: 144ms

▄▀▄▀▄▀▄▀▄▀▄▀

✓ Test pattern complete
  Events sent: 12
  Events received: 12
  Echo rate: 100.0%
  ✓ All events echoed back successfully!
```

### USB Hardware Test

**With actual USB keyer:**
```bash
python3 cw_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign SM5ABC \
  --mode iambic-b \
  --wpm 25 \
  --debug
```

### Multi-User Test (Echo Mode)
### Multi-User Test (Echo Mode)

⚠️ **IMPORTANT:** Cloudflare Workers free tier only supports **echo mode** (single WebSocket connection).

**What Echo Mode Means:**
```
Browser Client (ABC)      ─┐
                           ├─> Worker ─> Echo to SAME connection only
Python Client (SM0ONR)    ─┘
```

**Each connection is isolated:**
- Browser (ABC) sees only ABC's events echoed back
- Python (SM0ONR) sees only SM0ONR's events echoed back
- ❌ ABC and SM0ONR do NOT see each other's events

**Testing Browser Self-Echo:**

1. Open browser: http://localhost:8080
2. Enter callsign (e.g., ABC) and join room
3. Press Z or X keys for CW
4. **Check browser console** (F12) for:
   ```
   [TCP-TS] Received CW event: ABC key: true
   [Room] Received CW event from: ABC DOWN
   [Room] Playing event from jitter buffer: ABC
   [Room] Skipping own echo from jitter buffer
   ```
5. You should see:
   - ✓ Events sent (in stats)
   - ✓ Events received (in stats)
   - ✓ Decoder output (decoded text)
   - ⚠️ No sidetone from echo (local sidetone plays instead)

**Testing Python Client:**

```bash
python3 cw_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign SM0ONR \
  --mode straight \
  --debug
```

Python client will:
- ✓ See its own events echoed back
- ✓ Show 100% echo rate
- ❌ NOT visible in browser (separate connection)

**For True Multi-User (Cross-Client Communication):**
- Deploy Durable Objects ($5/mo)
- Or run Node.js relay server
- See PLATFORM_COMPARISON.md

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

**"Why don't I see Python client events in browser?"**
- This is EXPECTED in echo mode
- Each WebSocket connection is isolated
- Python client (SM0ONR) and browser (ABC) are separate connections
- Neither can see the other's events
- This is a Cloudflare Workers free tier limitation
- Solution: Use Durable Objects ($5/mo) or Node.js relay

**"Why don't I hear audio from echoed events?"**
- This is INTENTIONAL
- Browser skips audio for its own echoes (line 114 in room-controller.js)
- Local sidetone plays immediately when you press keys
- Echoed events are only for timing validation, not audio
- Remote users (in multi-user mode) WOULD hear your audio

**"Browser shows events sent but decoder shows nothing?"**
- Check browser console (F12) for errors
- Verify jitter buffer is processing events
- Check if decoder is receiving events:
  ```
  [Room] Playing event from jitter buffer: ABC
  ```
- Decoder needs valid CW timing (dit/dah patterns)

---

## USB Key Sender Testing

### Implementation Summary

Successfully implemented USB keyer sender for web platform using TCP-TS timing over WebSocket JSON.

**Files:**
- `cw_usb_key_sender_web.py` - Main USB key sender
- `test_usb_key_sender_web.py` - Simulated testing tool

### Echo Mode Test Results

**Configuration:**
```bash
python3 test_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign TEST \
  --wpm 25 \
  --debug
```

**Results:**
```
Test Pattern: "A A A" (3 letters, 12 events total)
Events sent: 12
Events received: 12
Echo rate: 100.0%

Latency: 0-2ms (avg 1.25ms)
Packet loss: 0%
Timing accuracy: ±1ms
```

**Performance:**
- ✅ TCP-TS timestamps working correctly
- ✅ WebSocket JSON format validated
- ✅ Sequence numbers incrementing
- ✅ Duration fields accurate (48ms dit, 144ms dah)
- ✅ Keepalive messages functioning
- ✅ Echo success rate 100%

### Test With Actual Hardware

```bash
# Straight key
python3 cw_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign SM5ABC \
  --mode straight

# Iambic Mode B (25 WPM)
python3 cw_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign SM5ABC \
  --mode iambic-b \
  --wpm 25 \
  --debug
```

**Serial Port:**
- Auto-detects if only one port
- Interactive menu if multiple ports
- Manual: `--port /dev/ttyUSB0`

**Pin Configuration:**
- CTS (pin 8): Dit paddle / Straight key
- DSR (pin 6): Dah paddle
- GND (pin 5): Common ground

### Latency Measurements

| Packet | Duration | Timestamp | Latency |
|--------|----------|-----------|---------|
| 0      | 48ms     | 0ms       | 0ms     |
| 1      | 48ms     | 49ms      | 1ms     |
| 2      | 144ms    | 98ms      | 1ms     |
| 3      | 144ms    | 244ms     | 1ms     |
| 4      | 48ms     | 582ms     | 1ms     |
| 5      | 48ms     | 630ms     | 2ms     |
| 6      | 144ms    | 680ms     | 1ms     |
| 7      | 144ms    | 825ms     | 2ms     |
| 8      | 48ms     | 1163ms    | 2ms     |
| 9      | 48ms     | 1212ms    | 1ms     |
| 10     | 144ms    | 1260ms    | 2ms     |
| 11     | 144ms    | 1406ms    | 1ms     |

**Average:** 1.25ms round-trip

### Protocol Validation

✅ **TCP-TS Timing:**
- Timestamps relative to transmission start
- First packet: ts=0ms
- Accurate cumulative timing
- Independent of arrival time (burst-resistant)

✅ **JSON Format:**
```json
{
  "type": "cw_event",
  "callsign": "TEST",
  "key_down": true,
  "duration_ms": 48,
  "timestamp_ms": 0,
  "sequence": 0
}
```

✅ **State Transitions:**
- DOWN → UP → DOWN → UP (alternating)
- No invalid state changes
- Duration matches CW timing (48ms dit @ 25 WPM)

### Known Limitations

⚠️ **Multi-user relay:** Echo mode only (Cloudflare Workers free tier limitation)
- Need Durable Objects ($5/mo) or Node.js server for multi-user
- Current implementation validates protocol correctness
- Ready for hardware testing in single-user mode

### Conclusion

✅ **Implementation successful!**
- USB key sender working correctly
- TCP-TS timing validated
- WebSocket JSON protocol confirmed
- Latency excellent (<2ms local)
- 100% packet delivery
- Timing accuracy ±1ms

Ready for production use once multi-user relay deployed.

---

## Complete Local Testing (December 12, 2025)

### Test Environment
- **Web Server:** http://localhost:8080 (Python http.server)
- **Worker:** ws://localhost:8787 (Cloudflare Workers Dev)
- **Mode:** Echo mode (single-user testing)

### Tests Performed

#### ✅ 1. Python Client Test
```bash
python3 test_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign PYTHON_CLIENT \
  --wpm 20
```

**Results:**
- ✅ Connection successful
- ✅ Sent 12 events (pattern "A A A")
- ✅ Received 12 events (100% echo rate)
- ✅ Latency: 0-2ms
- ✅ Timing accuracy: ±1ms

#### ✅ 2. Web Browser Test
- ✅ Landing page loads correctly
- ✅ JavaScript configured for localhost
- ✅ WebSocket connection to ws://localhost:8787
- ✅ Room interface functional

#### ✅ 3. Protocol Validation
- ✅ TCP-TS timestamps working (relative to start)
- ✅ WebSocket JSON format correct
- ✅ Sequence numbers incrementing
- ✅ Duration fields accurate
- ✅ State transitions valid (DOWN↔UP)

### Quick Start Commands

**Start servers:**
```bash
# Terminal 1: Web server
cd web_platform_tcp/public
python3 -m http.server 8080

# Terminal 2: Worker
cd web_platform_tcp/worker
npx wrangler dev
```

**Test in browser:**
```
http://localhost:8080
```

**Test with Python:**
```bash
python3 test_usb_key_sender_web.py \
  --server ws://localhost:8787 \
  --callsign TEST
```

**Stop servers:**
```bash
# Kill by PID or use Ctrl+C in each terminal
```

### Next Steps

1. ✅ Web platform functional locally
2. ✅ Python client working
3. ⚠️ Multi-user needs Durable Objects or Node.js
4. 📋 Hardware testing with USB keyer pending
5. 📋 Production deployment pending

---

**73 de SM0ONR** 📻

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

## USB Keyer Testing (Updated)

### Hardware Setup

**USB-Serial Adapter Connections:**
- **CTS (pin 8):** Dit paddle / Straight key
- **DSR (pin 6):** Dah paddle  
- **GND (pin 5):** Ground (common)

### Quick Test Scripts

**1. Using test script (easiest):**
```bash
# Straight key
./test-usb-keyer.sh straight

# Iambic Mode B at 25 WPM
./test-usb-keyer.sh iambic-b 25

# Iambic Mode A at 20 WPM
./test-usb-keyer.sh iambic-a 20
```

**2. Manual command:**
```bash
# Iambic Mode B
python3 cw_usb_key_sender_web.py \
    --server ws://localhost:8787 \
    --callsign SM0ONR \
    --port /dev/ttyUSB0 \
    --mode iambic-b \
    --wpm 25 \
    --debug

# Straight key
python3 cw_usb_key_sender_web.py \
    --server ws://localhost:8787 \
    --callsign SM0ONR \
    --port /dev/ttyUSB0 \
    --mode straight
```

### Iambic Keyer Implementation

**Thread Architecture:**
- Main async loop handles WebSocket communication
- Separate thread runs blocking keyer logic (time.sleep calls)
- Events queued from keyer thread, sent from async loop
- Prevents async event loop blocking

**Modes:**
- `iambic-a` - Mode A (no squeeze memory)
- `iambic-b` - Mode B (with squeeze memory between elements)

**Testing Iambic Keyer:**
1. Connect paddles to CTS (dit) and DSR (dah)
2. Run with `--mode iambic-b --wpm 25 --debug`
3. Press dit paddle - should send dits
4. Press dah paddle - should send dahs
5. Press both (squeeze) - should send alternating dit-dah-dit-dah
6. Check worker logs for "broadcasting to X other peers"
7. Open browser to see events arrive

### Troubleshooting Iambic Keyer

**Paddles backwards:**
- Dit and dah may be swapped
- Solution: Swap CTS/DSR connections or use --swap-paddles flag (if implemented)

**No response:**
```bash
# Test paddle state
python3 -c "import serial; s=serial.Serial('/dev/ttyUSB0'); print('CTS:', s.cts, 'DSR:', s.dsr)"

# Press dit paddle - CTS should be True
# Press dah paddle - DSR should be True
```

**Timing issues:**
- Adjust WPM: `--wpm 25`
- Try different mode: `--mode iambic-a` vs `--mode iambic-b`
- Check --debug output for event timing

**Thread errors:**
- Check console for "Keyer thread error"
- Verify serial port permissions: `ls -la /dev/ttyUSB0`
- Add to dialout group: `sudo usermod -a -G dialout $USER`

## Durable Objects Multi-User (Now Working!)

### What Changed

**Previous:** Echo mode - each connection isolated

**Current:** Durable Objects broadcast - true multi-user

### Verification

**1. Check worker startup:**
```bash
npx wrangler dev --local --port 8787
```

Look for:
```
Your Worker has access to the following bindings:
Binding                                               Resource            Mode
env.CW_ROOM (CWRoom, defined in cw-studio-relay)      Durable Object      local [connected]
```

**2. Test with multiple clients:**

Terminal 1 (Python client):
```bash
python3 test_usb_key_sender_web.py --server ws://localhost:8787 --callsign SM0ONR --wpm 25
```

Browser:
```
http://localhost:8080/room.html?callsign=ABC&room=main
```

**3. Expected worker logs:**
```
[CWRoom] ABC joined (1 total)
[CWRoom] SM0ONR joined (2 total)
[CWRoom] Broadcast peer_joined to 1 peers
[CWRoom] CW event from SM0ONR: DOWN, broadcasting to 1 other peers
[CWRoom] Broadcast cw_event to 1 peers
```

**4. Expected browser console:**
```
[TCP-TS] Peer joined: SM0ONR xxx-xxx-xxx
[TCP-TS] Received CW event: SM0ONR key: true dur: 48
[JitterBuffer] Adding event: SM0ONR key: true ts: 0
[Audio] setKey: SM0ONR keyDown: true
```

### Success Indicators

✅ Worker logs show "broadcasting to X other peers" (X > 0)
✅ Browser shows "Peer joined: [callsign]"
✅ Browser receives and plays CW events from other clients
✅ Decoder shows decoded text from other operators
✅ Multiple browser tabs can see each other

### Audio Permission Banner

Modern browsers require user interaction before playing audio.

**What you'll see:**
- Orange banner at top: "🔊 Click anywhere to enable audio"
- Console warnings: "AudioContext was not allowed to start"

**Solution:**
- Click "Enable Audio" button
- Or click anywhere on page
- Banner disappears, audio starts working

**Implementation:**
- Automatic banner display on first audio attempt
- Event listeners on button, body click, and keydown
- AudioContext.resume() called on user gesture

