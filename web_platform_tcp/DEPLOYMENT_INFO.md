# CW Studio - Cloudflare Deployment

## 🚀 Deployment Complete!

### Worker (WebSocket Relay)
- **Name:** cw-studio-relay
- **URL:** https://cw-studio-relay.data4-9de.workers.dev
- **Type:** Durable Objects-based WebSocket relay
- **Features:** 
  - Multi-user room support
  - Real-time CW event broadcasting
  - Peer connection management

### Pages (Web Application)
- **Name:** cw-studio
- **Production URL:** https://cw-studio.pages.dev
- **Latest Deployment:** https://75d25782.cw-studio.pages.dev
- **Features:**
  - Browser-based Morse code decoder
  - Manual keying (Z/X keys)
  - Automated text-to-CW sending
  - Jitter buffer with timestamp-based scheduling
  - Audio sidetone generation

## 🔧 Configuration

The Pages app automatically connects to:
- **Local development:** `ws://localhost:8787` (when running on localhost)
- **Production:** `wss://cw-studio-relay.data4-9de.workers.dev`

## 📝 Usage

### Access the Web App
1. Go to: https://cw-studio.pages.dev
2. Click "Enable Audio" 
3. Start keying with Z (dit) and X (dah) keys
4. Or send automated text

### Connect with Python Client
```bash
python3 test_usb_key_sender_web.py \
  --server wss://cw-studio-relay.data4-9de.workers.dev \
  --callsign SM0ONR \
  --wpm 25
```

## 🗑️ Cleanup

Successfully removed old projects:
- ✅ cw-studio-signaling (Worker)
- ✅ cw-studio (Worker)
- ✅ cw-signaling (Worker)
- ✅ event-batching (Worker - didn't exist)
- ⚠️ event-batching (Pages - needs manual cleanup in dashboard)
- ⚠️ cw-studio (old Pages - needs manual cleanup in dashboard)

## 🔄 Redeployment

### Worker
```bash
cd worker
npx wrangler deploy
```

### Pages
```bash
cd /home/tomas/Documents/Projekt/CW/protocol/web_platform_tcp
npx wrangler pages deploy public --project-name cw-studio --commit-dirty=true
```

## 🐛 Bug Fixes Applied

1. **Jitter Buffer Timeline Cleanup:** Added `removeSender()` method to clear timeline offset when peers disconnect
2. **Decoder State Cleanup:** Fixed `removeUser()` to receive callsign from `peer_left` event
3. **Morse Code Pattern:** Fixed 'P' pattern from `-.--` (Y) to `.--.]` (correct P)

## 📊 Architecture

```
Python Sender → WebSocket → Worker (Durable Objects) → WebSocket → Browser
                               ↓
                          Broadcasts to all peers in room
                               ↓
                Browser: Jitter Buffer → Audio Handler → Decoder
```

## ✅ Tested Features

- [x] WebSocket connection to worker
- [x] Multi-user room support
- [x] CW event broadcasting
- [x] Jitter buffer scheduling
- [x] Morse code decoding
- [x] Audio sidetone generation
- [x] Peer disconnect cleanup
- [x] Sender reconnection handling

## 📅 Deployed
Date: December 13, 2025
Version: v1.0
