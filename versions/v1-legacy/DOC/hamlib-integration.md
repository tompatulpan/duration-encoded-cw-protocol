# Hamlib Integration Guide for Remote Radio Operation

Complete guide for integrating Hamlib rig control with the duration-encoded CW protocol for remote QMX+ operation, including audio streaming solutions.

---

## Overview

This document describes a **three-system parallel architecture** for complete remote radio operation:

1. **CW Keying** - Duration-encoded protocol (this project) for real-time keying with operator timing preservation
2. **Rig Control** - Hamlib/rigctld for frequency, mode, and PTT control
3. **Audio Streaming** - P2P audio for monitoring and voice communication

All three systems operate **independently** over the network, each optimized for its specific task.

---

## Table of Contents

- [Hamlib Architecture](#hamlib-architecture)
- [System Components](#system-components)
- [Hardware Requirements](#hardware-requirements)
- [Audio Streaming Solutions](#audio-streaming-solutions)
- [Network Configuration](#network-configuration)
- [Complete Setup Example](#complete-setup-example)
- [Troubleshooting](#troubleshooting)

---

## Hamlib Architecture

### What is Hamlib?

Hamlib is a library providing a unified API for controlling amateur radio transceivers, rotators, and amplifiers. It supports 200+ radio models through "backend" drivers.

**Key Components:**

- **libhamlib** - Core library with unified API
- **rigctld** - Network daemon for remote rig control
- **rigctl** - Command-line client for rig control
- **Backend drivers** - Radio-specific implementations (Yaesu, Icom, Kenwood, etc.)

### How rigctld Works

```
Local Station                     Remote Station
┌──────────────┐                 ┌──────────────┐
│   rigctl     │──TCP:4532──────→│   rigctld    │
│  (client)    │   Commands       │   (daemon)   │
└──────────────┘                 │      ↓       │
                                 │  libhamlib   │
                                 │      ↓       │
                                 │  USB Serial  │
                                 │      ↓       │
                                 │  QMX+ Radio  │
                                 └──────────────┘
```

**Protocol**: Simple text-based commands over TCP
```
set_freq 14060000    # Set frequency to 14.060 MHz
set_mode CW 500      # Set mode to CW, 500Hz filter
get_freq             # Query current frequency
set_ptt 1            # PTT on
set_ptt 0            # PTT off
```

### CAT Command Latency

**Typical latencies:**
- USB/Serial connection: 10-50ms
- Network (rigctld): +10-30ms
- **Total over internet**: 20-80ms

**Important**: This latency is **acceptable** for frequency/mode changes but **not suitable** for real-time CW keying. That's why we use the separate duration-encoded CW protocol.

---

## System Components

### Three Independent Systems

```
┌─────────────────────────────────────────────────────────┐
│                    PARALLEL SYSTEMS                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. CW KEYING (Duration-Encoded Protocol)               │
│     ├─ Protocol: TCP port 7356 (timestamp variant)      │
│     ├─ Latency: 100-150ms (jitter buffer)               │
│     ├─ Purpose: Real-time keying with timing            │
│     └─ Bandwidth: ~2-3 kbps                             │
│                                                          │
│  2. RIG CONTROL (Hamlib)                                │
│     ├─ Protocol: TCP port 4532 (rigctld)                │
│     ├─ Latency: 20-80ms per command                     │
│     ├─ Purpose: Frequency, mode, PTT control            │
│     └─ Bandwidth: <1 kbps                               │
│                                                          │
│  3. AUDIO STREAMING (JackTrip/Opus)                     │
│     ├─ Protocol: UDP port 4464 (or custom)              │
│     ├─ Latency: 20-50ms                                 │
│     ├─ Purpose: Monitor audio, voice QSO                │
│     └─ Bandwidth: ~50-350 kbps (codec dependent)        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Why Three Separate Systems?

1. **CW Keying** - Requires precise timing preservation, jitter compensation, low protocol overhead
2. **Rig Control** - Infrequent commands, reliability more important than speed
3. **Audio** - Continuous streaming, different latency/buffer requirements

Combining them would compromise each system's optimization.

---

## Hardware Requirements

### Local Station (Operator)

**Option A: Laptop/Desktop PC**
- USB-to-serial adapter or XIAO SAMD21 for physical key
- Audio interface (built-in sound card sufficient)
- Network connection

**Option B: Raspberry Pi 4/5**
- Better for dedicated remote station
- Low power consumption
- GPIO available for direct key interface
- Can run all three systems simultaneously

### Remote Station (QMX+ Site)

**Required:**
- **Raspberry Pi 4 or 5** (recommended)
  - RPi 3 works but higher CPU load
  - 2GB RAM sufficient, 4GB better
- **USB cable** for QMX+ (provides CAT control + audio)
- **Opto-isolator circuit** for key input
  - 4N25 or similar
  - Protects RPi GPIO from voltage spikes
  - Electrical isolation between RPi and QMX+

**✨ QMX+ USB Sound Card Advantage:**
- **One USB cable does everything**: CAT control + RX audio + TX audio
- No external sound card needed (QMX+ has built-in USB audio interface)
- Cleaner installation, fewer cables
- No ground loop issues
- Lower cost (no separate USB sound card to buy)

**Circuit: RPi GPIO → QMX+ Key Input**
```
RPi GPIO17 ──[1kΩ]──┐
                     │
              LED side ── 4N25 opto-isolator
                     │
RPi GND ─────────────┘

Transistor side:
QMX+ Key TIP ────┐
                 │── 4N25 output
QMX+ Key RING ───┘
```

### QMX+ Configuration

- **Model ID for Hamlib**: 2049 (QRPLabs QMX+)
- **CAT Interface**: USB serial (appears as `/dev/ttyACM0` or `/dev/ttyUSB0` on Linux)
- **Baud Rate**: 38400 (default for QMX+) or 115200 (newer firmware)
- **Key Input**: 3.5mm jack (tip/ring/sleeve)
- **USB Audio**: Built-in 48kHz 24-bit USB sound card

### ⚠️ Critical Linux Setup for QMX+ USB Audio

**REQUIRED: Disable interfering Linux services**

Linux systems have services that interfere with QMX+ USB operation. These MUST be disabled before the QMX+ USB audio will work:

#### Problem: ModemManager

Linux detects the QMX+ serial port as a modem and sends Hayes AT-commands (from 1981!). This:
- Puts QMX+ into Terminal mode
- Disables CAT command processing
- Prevents digital modes software from working
- **Blocks USB audio from appearing**

**Solution - Permanently disable ModemManager:**

```bash
# On Raspberry Pi (required before QMX+ audio works!)
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
sudo systemctl mask ModemManager

# Verify it's disabled
sudo systemctl status ModemManager
# Should show: "Loaded: masked"
```

#### Problem: BRLTTY (Braille Service)

BRLTTY (Braille accessibility service) also interferes with USB devices, even if you don't use Braille displays.

**Solution - Permanently disable BRLTTY:**

```bash
# Disable BRLTTY services
sudo systemctl stop brltty-udev.service
sudo systemctl mask brltty-udev.service
# Output: Created symlink /etc/systemd/system/brltty-udev.service → /dev/null

sudo systemctl stop brltty.service
sudo systemctl disable brltty.service

# Verify disabled
sudo systemctl status brltty
```

#### Enable USB Audio on QMX+

After disabling the interfering services:

1. **Disconnect and reconnect QMX+ USB cable**
2. **On the QMX+ radio**, access the settings menu
3. **Disable IQ data output** (if enabled)
4. **Enable USB Audio mode**
   - Consult QMX+ manual for exact menu path
   - Typically: Settings → USB → Audio Enable
5. **Reboot the QMX+** if needed

#### Verify QMX+ Audio Detection

After the above steps, verify USB audio is working:

```bash
# Check USB device is detected
lsusb | grep -i "QRP\|QMX"
# Should show: Bus XXX Device XXX: ID 0483:a34c QRP Labs QMX Transceiver

# Check audio device appears
aplay -l | grep -i "QMX\|Transceiver\|USB"
# Should show something like:
# card 3: Transceiver [QMX Transceiver], device 0: USB Audio [USB Audio]

# Verify audio interfaces are present
lsusb -v -d 0483:a34c | grep -A 5 "Audio"
# Should show Audio Control and Streaming interfaces
```

**If audio device doesn't appear:**
- Check ModemManager and BRLTTY are fully disabled and masked
- Disconnect/reconnect USB cable
- Verify USB audio is enabled in QMX+ menu
- Check `dmesg | tail -30` for USB errors
- Try a different USB port on the Raspberry Pi

---

## Audio Streaming Solutions

### Comparison of P2P Audio Options

| Solution | Latency | Setup | NAT Handling | Quality | Full Duplex | Raspberry Pi |
|----------|---------|-------|--------------|---------|-------------|--------------|
| **JackTrip** | 20-40ms | Medium | Manual/port fwd | Excellent | ✅ Yes | ✅ Yes |
| **Opus/UDP DIY** | 20-60ms | Low | Manual | Excellent | ⚠️ Manual | ✅ Yes |
| **GStreamer RTP** | 20-100ms | Medium | Manual | Excellent | ⚠️ Manual | ✅ Yes |
| **WebRTC** | 30-80ms | High | Automatic | Good | ✅ Yes | ⚠️ Complex |
| **Zita-njbridge** | 5-50ms | Low | Manual | Excellent | ✅ Yes | ✅ Yes |

**Recommendation: JackTrip or GStreamer with Opus codec**

---

### Option 1: JackTrip (Recommended)

**Why JackTrip:**
- **Native full-duplex** - Simultaneous 2-way audio in single connection
- Designed for musicians (ultra-low latency critical)
- P2P connection after setup
- Works well on Raspberry Pi
- Active development and community support

#### Installation

```bash
# On both Raspberry Pis (local and remote)
sudo apt update
sudo apt install jacktrip

# Or build latest version
git clone https://github.com/jacktrip/jacktrip.git
cd jacktrip
./build
sudo make install
```

#### QMX+ USB Sound Card Integration

**The QMX+ has a built-in USB sound card** that appears as an audio device when connected via USB. This is the recommended audio interface for remote operation - **no external sound card needed!**

**Identifying the QMX+ Audio Device:**

```bash
# List all audio devices on Raspberry Pi
aplay -l

# Example output:
card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
card 3: Transceiver [QMX Transceiver], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0

# QMX+ appears as "QMX Transceiver" or "USB Audio Device"
# Card number varies! In this example: card 3, device 0 = hw:3,0
```

**⚠️ Important: Card Numbers Change!**

The QMX+ card number (hw:X,0) is **not fixed**. It depends on:
- USB connection order
- Other USB devices plugged in
- Raspberry Pi boot sequence

**Always check with `aplay -l` before configuring!** Common values:
- `hw:1,0` - If QMX+ is first USB audio device
- `hw:3,0` - If other USB devices or HDMI audio present
- `hw:2,0` - Another common assignment

For production use, consider using ALSA device names or udev rules for stable device identification.

**Audio Capabilities:**
- **Output (RX)**: QMX+ receiver audio → USB → Computer
- **Input (TX)**: Computer → USB → QMX+ transmitter (voice/digital modes)
- **Sample Rate**: 48kHz
- **Bit Depth**: 24-bit (S24_3LE format)
- **Channels**: 2 (stereo, but typically mono signal)

**Testing QMX+ Audio:**

```bash
# IMPORTANT: Replace hw:X,0 with your actual card number from 'aplay -l'
# Examples: hw:1,0, hw:2,0, hw:3,0

# Test playback (you should hear a tone on QMX+ speaker/headphones)
speaker-test -D hw:3,0 -c 2 -t sine -f 700 # Not working

# Test recording (monitor RX audio - tune QMX+ to active frequency first)
# QMX+ uses 24-bit audio format (S24_3LE)
arecord -D hw:3,0 -f S24_3LE -r 48000 -c 2 -d 5 /tmp/qmx_test.wav

# Play back the recording (on RPi headphones or via SSH)
aplay /tmp/qmx_test.wav

# Or copy to local machine for playback
scp pi@192.168.1.202:/tmp/qmx_test.wav .
aplay qmx_test.wav
```

**If recording fails with "Sample format non available":**
- You're using wrong audio format (S16_LE won't work)
- QMX+ requires S24_3LE (24-bit, 3-byte little-endian)
- Always use `-f S24_3LE` with QMX+ audio

**Complete Audio Path:**

```
REMOTE STATION (QMX+ Site):
┌───────────────────────────────────────────────┐
│ QMX+ Radio                                    │
│   RX Audio Out ──→ USB Sound Card ──→ USB    │
│   TX Audio In  ←── USB Sound Card ←── USB    │
└───────────────────────────────────────────────┘
         ↓ USB Cable (CAT + Audio combined!)
┌───────────────────────────────────────────────┐
│ Raspberry Pi 4                                │
│   /dev/snd/... (hw:1,0)                      │
│        ↓                                      │
│   JackTrip Server                             │
│        ↓                                      │
│   Network (UDP:4464)                          │
└───────────────────────────────────────────────┘
         ↓ Internet/LAN
┌───────────────────────────────────────────────┐
│ LOCAL STATION (Operator)                      │
│   JackTrip Client                             │
│        ↓                                      │
│   Sound Card / Speakers                       │
│        ↓                                      │
│   Your Ears + WSJT-X (waterfall)             │
└───────────────────────────────────────────────┘
```

**Key Advantage: Single USB Cable**
- One USB cable provides both CAT control AND audio
- No separate audio cables needed
- Cleaner installation
- Less chance of ground loops

#### Configuration

**⚠️ JackTrip Version Compatibility Warning**

JackTrip has different builds with incompatible options:

- **JACK-only builds** (e.g., v2.5.1 on Debian/Raspberry Pi OS)
  - Require JACK audio server running
  - NO `-R` (RtAudio) flag
  - NO direct device specification (`-I`/`-O` options don't exist or mean different things)
  
- **RtAudio-enabled builds** (e.g., v2.7.0 on some systems)
  - Can use system audio directly with `-R` flag
  - Supports `--audiodevice` option
  - Optional JACK support

**Check your version:**
```bash
jacktrip --version
jacktrip --help | grep -i "rtaudio\|jack"
```

---

### Method 1: JACK-Based Setup (Raspberry Pi Default)

**Use this if:** Your JackTrip version is 2.5.x or doesn't have `-R` option.

**Remote RPi (at QMX+ location):**

```bash
# Step 1: Install JACK if not already installed
sudo apt install jackd2

# Step 2: Find QMX+ card number (CRITICAL - changes per system!)
aplay -l | grep -i "QMX\|Transceiver"
# Note the card number, e.g., "card 3" means hw:3,0

# Step 3: Start JACK daemon with QMX+ device
# Use realtime priority (-R) and audio reservation bypass for stability
# Replace hw:3,0 with YOUR card number!
JACK_NO_AUDIO_RESERVATION=1 jackd -R -d alsa -d hw:3,0 -r 48000 -p 256 -n 3 &

# Wait for JACK to start (realtime needs longer)
sleep 5

# Step 4: Start JackTrip server (connects to JACK automatically)
jacktrip -s -q 16 --udprt &

# Step 5: Verify JACK connections
jack_lsp -c
# Should show:
#   system:capture_1 → JackTrip:send_1
#   system:capture_2 → JackTrip:send_2
#   JackTrip:receive_1 → system:playback_1
#   JackTrip:receive_2 → system:playback_2
```

**Local PC/RPi (operator location):**

```bash
# Method A: If you have RtAudio support (-R flag exists)
jacktrip -c <remote-ip> -q 16 --udprt -R

# Method B: If no RtAudio, use JACK on client too
jackd -d alsa -d hw:0,0 -r 48000 -p 256 &
sleep 2
jacktrip -c <remote-ip> -q 16 --udprt
```

**Options explained:**
- `-s` = server mode
- `-c <ip>` = client mode
- `-q 16` = queue buffer (16 packets ≈ 80ms latency) - **recommended for stability**
- `-q 8` = smaller buffer (≈ 40ms latency) - for very low latency needs
- `-q 4` = minimal buffer (≈ 20ms latency) - only for perfect networks
- `--udprt` = UDP realtime mode
- `-R` = use RtAudio (system audio) instead of JACK

---

### Method 2: RtAudio Direct Mode (Client Only)

**Use this if:** Client has v2.7.0+ with RtAudio support (`--help` shows `-R` option).

**Simpler client connection (no JACK needed on client):**

```bash
# List available audio devices
jacktrip --listdevices

# Connect using system default audio
jacktrip -c <remote-ip> -q 4 --udprt -R

# Or specify audio device explicitly
jacktrip -c <remote-ip> -q 4 --udprt -R --audiodevice "HD-Audio Generic (ALC897 Analog)"
```

**Server still needs JACK daemon** (Method 1 above) if it's using v2.5.x.

---

#### Audio Routing (QMX+ USB Sound Card)

**⚠️ The `-I` and `-O` options in standard Debian/RPi JackTrip do NOT specify audio devices!**

In JackTrip v2.5.x (common on Raspberry Pi):
- `-I` = `--iostat` (statistics reporting, NOT input device)
- `-O` = `--overflowlimiting` (audio limiter, NOT output device)

Device selection is handled by JACK, not JackTrip command-line options.

**Correct method - Audio routing via JACK:**

```bash
# Find QMX+ device first
aplay -l | grep -i "usb\|qmx"
# Note card number (e.g., card 3)

# Start JACK with QMX+ device
jackd -d alsa -d hw:3,0 -r 48000 -p 128 &
sleep 2

# Start JackTrip (connects to JACK automatically)
jacktrip -s -q 4 --udprt &

# JACK automatically routes:
#   QMX+ capture → JackTrip send → network
#   Network → JackTrip receive → QMX+ playback

# Verify routing
jack_lsp -c
```

**If you need manual JACK routing:**

```bash
# Install JACK connection tools
sudo apt install qjackctl

# Or use command-line
jack_connect system:capture_1 JackTrip:send_1
jack_connect system:capture_2 JackTrip:send_2
jack_connect JackTrip:receive_1 system:playback_1
jack_connect JackTrip:receive_2 system:playback_2
```

**Full Duplex (2-Way Audio for FT8/Voice Operation):**

**Why Full Duplex is Essential for FT8:**
- **RX Direction**: QMX+ receiver audio → Your computer (for WSJT-X decoding)
- **TX Direction**: Your computer → QMX+ transmitter (for FT8/voice transmission)
- **Both needed**: WSJT-X generates FT8 signals on your computer, sends to QMX+ for transmission

**Remote RPi - Full duplex is automatic with JACK:**

```bash
# JACK provides full duplex automatically
# When you start JACK with QMX+ device:
jackd -d alsa -d hw:3,0 -r 48000 -p 128 &
jacktrip -s -q 4 --udprt &

# This provides:
# ✅ QMX+ RX → JackTrip → Network (monitoring)
# ✅ Network → JackTrip → QMX+ TX (voice/FT8)

# No special flags needed! JACK handles bidirectional audio.

# Full duplex enables:
#   - CW operation (monitoring only)
#   - FT8/FT4 operation (RX decode + TX generate)
#   - Voice QSOs (SSB, AM, FM)
#   - Digital modes (PSK31, RTTY via fldigi)
```

**Local station - Full Duplex for FT8:**

```bash
# Method 1: RtAudio mode (if supported)
jacktrip -c <remote-ip> -q 4 --udprt -R
# Uses system default audio device for both RX and TX

# Method 2: JACK mode (alternative)
jackd -d alsa -d hw:0,0 -r 48000 -p 128 &
jacktrip -c <remote-ip> -q 4 --udprt
# JACK provides full duplex automatically

# Both methods provide:
# ✅ QMX+ RX → Your speakers + WSJT-X input (monitoring/decoding)
# ✅ WSJT-X output → QMX+ TX (transmission)
```

**Audio Flow for FT8 Operation:**

```
┌──────────────────────────────────────────────────────────┐
│                    RX PATH (Receive)                      │
└──────────────────────────────────────────────────────────┘
QMX+ Receiver → USB Audio Out → JackTrip → Network
                                              ↓
                            Local PC ← JackTrip Client
                                    ↓
                        ┌───────────┴──────────────┐
                        ↓                      ↓
                   Speakers              WSJT-X Input
                   (Monitor)             (Decode FT8)

┌──────────────────────────────────────────────────────────┐
│                    TX PATH (Transmit)                     │
└──────────────────────────────────────────────────────────┘
WSJT-X (Generate FT8) → Sound Card Output → JackTrip
                                              ↓
                                          Network
                                              ↓
                          Remote JackTrip → QMX+ USB Audio In
                                              ↓
                                      QMX+ Transmitter
                                              ↓
                                          Antenna
```

**Audio Levels:**

```bash
# Adjust QMX+ audio input level on remote RPi
alsamixer
# Press F6, select "USB Audio Device"
# Adjust capture level (typically 70-90%)

# Or via command line:
amixer -c 1 sset 'Mic' 80%
```

**Systemd Service for Auto-start (Remote RPi):**

```bash
# Create service file
sudo nano /etc/systemd/system/jacktrip-qmx.service
```

```ini
[Unit]
Description=JackTrip Audio for QMX+
After=network.target sound.target

[Service]
Type=simple
User=pi
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/jacktrip -s -q 4 --udprt -I hw:1,0 -O hw:1,0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable jacktrip-qmx
sudo systemctl start jacktrip-qmx

# Check status
sudo systemctl status jacktrip-qmx
```

```bash
# Remote: QMX+ audio in both directions
jacktrip -s -q 4 --udprt -I hw:1,0 -O hw:1,0

# -I hw:1,0 = Input: Capture QMX+ RX audio → send to network
# -O hw:1,0 = Output: Receive from network → play to QMX+ TX audio

# This allows:
#   - Operator hears QMX+ RX (monitoring)
#   - Operator voice goes to QMX+ TX (voice QSOs)
```

**Local station - Receive audio from network:**

```bash
# Find your local audio device
aplay -l

# Example: Built-in audio = hw:0,0
# Connect to remote JackTrip
jacktrip -c <remote-ip> -q 4 --udprt -O hw:0,0

# For full duplex (send mic, receive QMX+ audio):
jacktrip -c <remote-ip> -q 4 --udprt -I hw:0,0 -O hw:0,0

# -I hw:0,0 = Input: Your microphone → send to remote
# -O hw:0,0 = Output: QMX+ RX audio → your speakers
```

**Audio Levels:**

```bash
# Adjust QMX+ audio input level on remote RPi
alsamixer
# Press F6, select "USB Audio Device"
# Adjust capture level (typically 70-90%)

# Or via command line:
amixer -c 1 sset 'Mic' 80%
```

**Systemd Service for Auto-start (Remote RPi):**

```bash
# Create service file
sudo nano /etc/systemd/system/jacktrip-qmx.service
```

```ini
[Unit]
Description=JackTrip Audio for QMX+
After=network.target sound.target

[Service]
Type=simple
User=pi
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/jacktrip -s -q 4 --udprt -I hw:1,0 -O hw:1,0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable jacktrip-qmx
sudo systemctl start jacktrip-qmx

# Check status
sudo systemctl status jacktrip-qmx
```

#### Full Duplex (2-Way Audio)

**JackTrip inherently supports bidirectional audio** - both stations can transmit and receive simultaneously.

**Use cases:**
- Operator speaks to remote station while monitoring QMX+ RX audio
- Voice communication during CW operation
- Full QSO capability (voice + CW mixed)

**With JACK-based setup (recommended for Raspberry Pi):**
```bash
# Remote: JACK provides full duplex automatically
jackd -d alsa -d hw:3,0 -r 48000 -p 128 &
jacktrip -s -q 4 --udprt

# Local: Use RtAudio mode or JACK
jacktrip -c <remote-ip> -q 4 --udprt -R

# Single UDP connection handles both directions!
# JACK automatically routes bidirectional audio
```

---

### Option 2: GStreamer with Opus Codec

**Why GStreamer:**
- Lower bandwidth (48 kbps with Opus)
- Standard RTP protocol
- Fine-grained control
- Professional-grade

#### Installation

```bash
sudo apt install gstreamer1.0-tools \
                 gstreamer1.0-plugins-good \
                 gstreamer1.0-plugins-bad \
                 gstreamer1.0-plugins-ugly \
                 gstreamer1.0-libav
```

#### Remote → Local (QMX+ RX audio)

**Remote RPi (sender):**
```bash
gst-launch-1.0 alsasrc device=hw:1,0 ! \
  audioconvert ! audioresample ! \
  opusenc bitrate=48000 ! rtpopuspay ! \
  udpsink host=<local-ip> port=5004
```

**Local station (receiver):**
```bash
gst-launch-1.0 udpsrc port=5004 caps="application/x-rtp" ! \
  rtpopusdepay ! opusdec ! \
  audioconvert ! alsasink device=hw:0,0
```

#### Local → Remote (Operator voice)

Add second pipeline with different port (e.g., 5006).

---

### Option 3: Simple Opus over UDP (DIY)

For integration into existing Python code:

```python
#!/usr/bin/env python3
"""Simple P2P audio with Opus codec"""
import socket
import pyaudio
import opuslib

SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_SIZE = 960  # 20ms at 48kHz

# Initialize
audio = pyaudio.PyAudio()
encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_AUDIO)
decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Transmit thread
def tx_audio(remote_ip, remote_port):
    stream = audio.open(format=pyaudio.paInt16, channels=1, 
                       rate=SAMPLE_RATE, input=True, 
                       frames_per_buffer=FRAME_SIZE)
    while True:
        pcm = stream.read(FRAME_SIZE)
        opus_data = encoder.encode(pcm, FRAME_SIZE)
        sock.sendto(opus_data, (remote_ip, remote_port))

# Receive thread
def rx_audio(local_port):
    sock.bind(('0.0.0.0', local_port))
    stream = audio.open(format=pyaudio.paInt16, channels=1, 
                       rate=SAMPLE_RATE, output=True)
    while True:
        opus_data, addr = sock.recvfrom(4096)
        pcm = decoder.decode(opus_data, FRAME_SIZE)
        stream.write(pcm)
```

**Dependencies:**
```bash
pip3 install opuslib pyaudio
sudo apt install libopus0 libopus-dev
```

---

## Network Configuration

### Required Network Setup

Three TCP/UDP ports need to be accessible:

```
Service          | Protocol | Port | Direction        | Purpose
-----------------|----------|------|------------------|------------------
CW Protocol      | TCP      | 7356 | Local → Remote   | Keying commands
Hamlib (rigctld) | TCP      | 4532 | Local → Remote   | Rig control
Audio (JackTrip)| UDP      | 4464 | Bidirectional    | Audio streaming
```

---

### Option A: Port Forwarding (Traditional)

**Best for**: Stable home connection with public IP or port forward capability

#### Remote Router Configuration

Forward these ports to remote Raspberry Pi (e.g., 192.168.1.100):

```
External Port  →  Internal IP:Port       Protocol
───────────────────────────────────────────────────
7356           →  192.168.1.100:7356    TCP
4532           →  192.168.1.100:4532    TCP
4464           →  192.168.1.100:4464    UDP
```

**Router access**: Usually http://192.168.1.1 or http://192.168.0.1

#### Dynamic DNS Setup

If remote site has dynamic IP address:

**DuckDNS (Free, easy):**
```bash
# On remote RPi
mkdir ~/duckdns
cd ~/duckdns
echo "domains=yourname
token=your-duckdns-token" > duck.conf

# Create update script
echo "curl -k https://www.duckdns.org/update/\
yourname/your-token" > duck.sh
chmod +x duck.sh

# Add to crontab (update every 5 minutes)
crontab -e
# Add line:
*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1
```

Then use `yourname.duckdns.org` instead of IP address.

#### Firewall Configuration

**Remote RPi:**
```bash
sudo ufw allow 7356/tcp   # CW protocol
sudo ufw allow 4532/tcp   # Hamlib
sudo ufw allow 4464/udp   # JackTrip audio
sudo ufw enable
```

---

### Option B: Tailscale VPN (Modern, Recommended)

**Best for**: 
- CGNAT connections (no public IP)
- Corporate networks (restricted)
- Mobile operation
- "Zero configuration" preference

#### Why Tailscale?

- **Zero configuration** - Works through NAT automatically
- **Peer-to-peer** - Direct connection after setup (not relayed)
- **Encrypted** - WireGuard-based VPN
- **Free** for personal use (up to 20 devices)
- **Just works** - No router configuration needed

#### Installation

**On both Raspberry Pis (local and remote):**

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start and authenticate (opens browser)
sudo tailscale up

# Get your Tailscale IP
tailscale ip -4
# Example output: 100.64.0.1
```

#### Usage

After setup, use **Tailscale IPs** instead of public IPs:

```bash
# CW sender - use Tailscale IP
python3 cw_usb_key_sender_tcp_ts.py 100.64.0.5

# Hamlib control
rigctl -m 2 -r 100.64.0.5:4532

# JackTrip
jacktrip -c 100.64.0.5 -q 4
```

**Advantages:**
- No port forwarding needed
- Works from anywhere (home, hotel, mobile)
- Automatic reconnection
- Built-in firewall (only your devices can connect)

**Latency impact:** Typically +5-15ms vs direct connection (minimal)

---

### Testing Network Connectivity

Before running full setup, test each port:

#### Test TCP Ports

```bash
# Remote RPi - listen
nc -l 7356  # CW protocol port

# Local station - connect
echo "test" | nc <remote-ip> 7356
```

If "test" appears on remote → TCP working!

#### Test UDP Ports

```bash
# Remote RPi - listen
nc -u -l 4464  # JackTrip port

# Local station - send
echo "test" | nc -u <remote-ip> 4464
```

If "test" appears → UDP working!

---

## Server Setup Script

**Automated script for starting JACK + JackTrip on the server (Raspberry Pi).**

### Installation

```bash
# Copy script to home directory
cp remote-audio-server.sh ~/
chmod +x ~/remote-audio-server.sh
```

### Usage

**Basic usage (auto-detect QMX+):**
```bash
# Start server with QMX+ device
~/remote-audio-server.sh

# Script will:
# 1. Find QMX+ audio device automatically
# 2. Check for service conflicts (ModemManager, BRLTTY)
# 3. Stop any existing JACK/JackTrip processes
# 4. Start JACK with QMX+ device
# 5. Start JackTrip server
# 6. Verify audio routing
# 7. Display status and connection info
```

**Test mode (without QMX+):**
```bash
# Run in test mode with metronome
~/remote-audio-server.sh --test

# Uses dummy audio device
# Generates 120 BPM metronome for testing
# Perfect for verifying client audio works
```

**Advanced options:**
```bash
# Specify device manually
~/remote-audio-server.sh --device hw:3,0

# Adjust sample rate
~/remote-audio-server.sh --rate 44100

# Larger buffer for internet connections
~/remote-audio-server.sh --queue 8

# Combine options
~/remote-audio-server.sh --device hw:3,0 --queue 8
```

**Get help:**
```bash
~/remote-audio-server.sh --help
```

### Output Example

```
═══════════════════════════════════════════
  Remote Audio Server Setup
  JACK + JackTrip for QMX+ Remote Operation
═══════════════════════════════════════════

ℹ Searching for QMX+ audio device...
✓ Found audio device: hw:3,0
card 3: TransceiverQMX [QMX+ Transceiver], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
ℹ Checking for service conflicts...
✓ No service conflicts detected
ℹ Stopping existing JACK and JackTrip processes...
✓ Services stopped
ℹ Starting JACK audio server...
✓ JACK running (PID: 1234)

ℹ Available JACK ports:
system:capture_1
system:capture_2
system:playback_1
system:playback_2
ℹ Starting JackTrip server...
✓ JackTrip server running (PID: 1235)
ℹ Verifying JACK audio routing...

ℹ JACK connection graph:
system:capture_1
   JackTrip:send_1
system:capture_2
   JackTrip:send_2
JackTrip:send_1
   system:capture_1
...
✓ Audio routing appears correct

═══════════════════════════════════════════
  🎵 Remote Audio Server Status
═══════════════════════════════════════════
  Audio Device: hw:3,0
  Sample Rate: 48000 Hz
  Buffer Size: 128 samples
  JackTrip Port: UDP 4464
  Queue Buffer: 4 packets (~20ms)
═══════════════════════════════════════════

✓ JACK daemon: Running (PID: 1234)
✓ JackTrip server: Running (PID: 1235)

═══════════════════════════════════════════

ℹ Server is ready for connections!

Client connection command:
  jacktrip -c 192.168.1.201 -q 4 --udprt -R

Press Ctrl+C to stop server
```

### Features

✅ **Auto-detection** - Finds QMX+ device automatically  
✅ **Service conflict checking** - Warns about ModemManager/BRLTTY  
✅ **Clean restart** - Stops existing processes before starting  
✅ **Connection verification** - Checks JACK routing is correct  
✅ **Test mode** - Verify setup without hardware  
✅ **Configurable** - Override defaults via command line  
✅ **Error handling** - Clear error messages and suggestions  
✅ **Status display** - Shows all running services  

### Integration with System Startup

**Create systemd service for auto-start:**

```bash
sudo nano /etc/systemd/system/remote-audio.service
```

Add:
```ini
[Unit]
Description=Remote Audio Server (JACK + JackTrip)
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User=tomas
ExecStart=/home/tomas/remote-audio-server.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable remote-audio.service
sudo systemctl start remote-audio.service

# Check status
sudo systemctl status remote-audio.service
```

### Troubleshooting the Script

**Problem**: "No audio device found"

**Solution**: 
```bash
# List devices manually
aplay -l

# Specify device explicitly
~/remote-audio-server.sh --device hw:X,0  # Replace X with your card number
```

**Problem**: "JACK failed to start"

**Solution**:
```bash
# Check if device is busy
fuser -v /dev/snd/*

# Kill processes using audio device
sudo fuser -k /dev/snd/pcmC3D0c  # Adjust card number

# Restart script
~/remote-audio-server.sh
```

**Problem**: ModemManager/BRLTTY warnings

**Solution**:
```bash
# Disable conflicting services permanently
sudo systemctl mask ModemManager
sudo systemctl mask brltty

# Reboot or restart script
~/remote-audio-server.sh
```

---

## Complete Setup Example

### Remote Station (QMX+ Site) - Raspberry Pi 4

#### 1. Hardware Connections

```
QMX+                    Raspberry Pi 4              External
───────────────────────────────────────────────────────────
USB (CAT + Audio)  →    USB port (single cable!)   
Key Jack           ←    GPIO 17 (via opto-isolator)
Power              →    12V supply                  → 5V buck → RPi
                                                    → Antenna

Note: QMX+ USB provides both:
  - CAT control (/dev/ttyUSB0)
  - Audio I/O (hw:1,0 typically)
```

#### 2. Software Installation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install CW protocol dependencies
sudo apt install python3 python3-pip git
pip3 install pyaudio numpy

# Clone CW protocol repository
cd ~
git clone https://github.com/yourusername/cw-protocol.git
cd cw-protocol

# Install Hamlib (pi/debian)
sudo apt install libhamlib-utils

# Install Hamlib (fedora)
sudo dnf install hamlib

# Jacktrip dependencies (pi debian)
sudo apt install jackd2 qjackctl

# Install JackTrip (pi/debian)
sudo apt install jacktrip

# Install JackTrip (Fedora)
sudo dnf install jacktrip

# Install Tailscale (optional but recommended)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

#### 3. Configuration Files

**Create launcher script: `~/remote-station.sh`**

```bash
#!/bin/bash
# Remote Station Launcher

echo "Starting Remote Radio Station..."

# Check for QMX+ prerequisites
echo "Checking QMX+ Linux setup..."

# Check ModemManager
if systemctl is-active --quiet ModemManager; then
    echo "❌ WARNING: ModemManager is running! This will break QMX+ USB audio."
    echo "   Run: sudo systemctl mask ModemManager"
    exit 1
fi

# Check BRLTTY
if systemctl is-active --quiet brltty; then
    echo "❌ WARNING: BRLTTY is running! This may interfere with QMX+."
    echo "   Run: sudo systemctl mask brltty"
fi

echo "✓ Linux services OK"

# Get Tailscale IP (or use static IP)
REMOTE_IP=$(tailscale ip -4 2>/dev/null || hostname -I | awk '{print $1}')
echo "Station IP: $REMOTE_IP"

# Find QMX+ audio device
echo "Detecting QMX+ audio device..."
QMX_CARD=$(aplay -l | grep -i "QMX\|Transceiver" | grep -o "card [0-9]" | awk '{print $2}' | head -1)

if [ -z "$QMX_CARD" ]; then
    echo "❌ ERROR: QMX+ audio device not found!"
    echo "   Check: 1) USB cable connected"
    echo "          2) ModemManager disabled"
    echo "          3) USB audio enabled on QMX+ menu"
    echo "   Run 'aplay -l' to see available devices"
    exit 1
fi

echo "✓ Found QMX+ at hw:$QMX_CARD,0"

# 1. Start Hamlib rigctld
echo "Starting rigctld for QMX+..."
# QMX+ uses hamlib model 2057
rigctld -m 2057 -r /dev/ttyACM0 -s 115200 -t 4532 &
RIGCTLD_PID=$!
sleep 2

# 2. Start CW receiver with GPIO output
echo "Starting CW receiver on port 7356..."
cd ~/cw-protocol 2>/dev/null || cd ~/
python3 cw_gpio_output_tcp_ts.py --port 7356 --gpio 17 --jitter-buffer 150 &
CW_PID=$!

# 3. Start JACK audio server with QMX+
echo "Starting JACK audio server with QMX+ (hw:$QMX_CARD,0)..."
jackd -d alsa -d hw:$QMX_CARD,0 -r 48000 -p 128 &
JACK_PID=$!
sleep 3

# 4. Start JackTrip audio server
echo "Starting JackTrip audio server..."
jacktrip -s -q 4 --udprt &
JACKTRIP_PID=$!
sleep 2

# Verify JACK connections
echo "Verifying JACK audio routing..."
jack_lsp -c 2>/dev/null || echo "(jack_lsp not available, connections may need manual check)"

echo ""
echo "═══════════════════════════════════════════"
echo "  Remote Station Ready!"
echo "═══════════════════════════════════════════"
echo "  IP Address: $REMOTE_IP"
echo "  QMX+ Audio: hw:$QMX_CARD,0"
echo "  CW Protocol: TCP port 7356"
echo "  Hamlib:      TCP port 4532"
echo "  Audio:       UDP port 4464 (JackTrip)"
echo "═══════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "echo 'Stopping services...'; kill $RIGCTLD_PID $CW_PID $JACK_PID $JACKTRIP_PID 2>/dev/null; exit" INT
wait
```

```bash
chmod +x ~/remote-station.sh
```

#### 4. Auto-start on Boot (Optional)

```bash
# Create systemd service
sudo nano /etc/systemd/system/remote-station.service
```

```ini
[Unit]
Description=Remote Radio Station
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/home/pi/remote-station.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable remote-station
sudo systemctl start remote-station
```

---

### Local Station (Operator) - PC or Raspberry Pi

#### 1. Software Installation

```bash
# Install CW protocol
pip3 install pyaudio numpy

# Install Hamlib client
sudo apt install hamlib-utils

# Install flrig (GUI for rig control)
sudo apt install flrig

# Install JackTrip
sudo apt install jacktrip
```

#### 2. Configuration File

**Edit `cw_sender.ini`:**

```ini
[network]
host = 100.64.0.5        # Remote Tailscale IP (or public IP)
port = 7356              # TCP timestamp protocol
protocol = tcp-ts

[operator]
callsign = SM5ABC

[keyer]
mode = iambic-b
wpm = 25

[serial]
port =                   # Auto-detect USB key
auto_detect = yes

[audio]
enabled = yes           # Local sidetone
tx_frequency = 600
rx_frequency = 700
volume = 0.3
```

#### 3. Launcher Script: `~/local-station.sh`

```bash
#!/bin/bash
# Local Station Launcher

REMOTE_IP="100.64.0.5"  # Change to your remote IP

echo "Connecting to Remote Station at $REMOTE_IP..."

# 1. Start CW sender (USB key)
echo "Starting CW sender..."
cd ~/cw-protocol
python3 cw_usb_key_sender_tcp_ts.py $REMOTE_IP &
CW_PID=$!

# 2. Start JackTrip client (audio)
echo "Starting JackTrip audio..."
jacktrip -c $REMOTE_IP -q 4 --udprt &
JACKTRIP_PID=$!

echo ""
echo "═══════════════════════════════════════════"
echo "  Local Station Connected!"
echo "═══════════════════════════════════════════"
echo "  Remote: $REMOTE_IP"
echo "  CW: Active"
echo "  Audio: Active"
echo ""
echo "  Rig control commands:"
echo "    rigctl -m 2 -r $REMOTE_IP:4532"
echo "═══════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to disconnect"

trap "kill $CW_PID $JACKTRIP_PID; exit" INT
wait
```

```bash
chmod +x ~/local-station.sh
```

#### 4. Rig Control Commands

**Interactive mode:**
```bash
rigctl -m 2 -r 100.64.0.5:4532
```

**Common commands:**
```
Rig command: F 14060000        # Set frequency
Rig command: M CW 500          # Set mode
Rig command: f                 # Get frequency
Rig command: m                 # Get mode
Rig command: T 1               # PTT on
Rig command: T 0               # PTT off
Rig command: q                 # Quit
```

**Script example:**
```bash
#!/bin/bash
# QSY to 40m CW
echo "F 7030000" | rigctl -m 2 -r 100.64.0.5:4532
echo "M CW 500" | rigctl -m 2 -r 100.64.0.5:4532
```

#### 5. GUI Integration with flrig

For easier rig control, use a graphical interface instead of command-line.

**flrig** - Recommended GUI for Hamlib integration:

**What is flrig:**
- **Rig control GUI only** - Dedicated transceiver control interface
- Part of W1HKJ software suite (separate from fldigi digital modes)
- Not a digital modes program - just rig control

**Why flrig:**
- Clean, simple interface focused on rig control
- Direct Hamlib support via rigctld
- Cross-platform (Linux, Windows, macOS)
- Memory channels, band stack
- VFO A/B switching
- Active development by W1HKJ

**Not to be confused with:**
- **fldigi** - Digital modes software (PSK31, RTTY, etc.)
  - Separate program that can optionally use flrig for rig control
  - Not needed for CW remote operation unless you want digital modes

**Installation:**

```bash
# Ubuntu/Debian - installs flrig only
sudo apt install flrig

# Note: This does NOT install fldigi (digital modes)
# If you also want fldigi: sudo apt install fldigi

# Fedora
sudo dnf install flrig

# Or build from source
git clone https://github.com/w1hkj/flrig.git
cd flrig
./configure
make
sudo make install
```

**Configuration:**

1. Start flrig
2. Configure → Setup → Transceiver tab:
   - **Transceiver**: Hamlib NET rigctl
   - **Device**: `100.64.0.5:4532` (your rigctld address:port)
   - **Baud**: (not used for network)
   - **Poll interval**: 200ms (default)

3. Test connection:
   - Click "Initialize"
   - Should show "Online" status
   - Frequency and mode should display

**Alternative: Access remote rigctld directly without flrig**

flrig can also connect directly to QMX+ if you prefer:
- **Transceiver**: QRP QMX (if supported in your flrig version)
- **Device**: Select via Hamlib backend
- But this requires flrig running on remote RPi

**Recommended setup: flrig on local station → rigctld on remote**

This keeps GUI on your local computer while rigctld manages the radio remotely.

**Other GUI Options:**

| GUI | Platform | Features | Hamlib Support |
|-----|----------|----------|----------------|
| **flrig** | Linux/Win/Mac | Simple, fast | ✅ Native (rigctld) |
| **Grig** | Linux | Basic control | ✅ Native (libhamlib) |
| **DXLab Commander** | Windows | Full suite | ✅ Via Omni-Rig |
| **Ham Radio Deluxe** | Windows | Commercial | ✅ Native |
| **CAT4Linux** | Linux | Web interface | ✅ Native |

**flrig Advantages for Remote Operation:**
- Network-transparent (works same for local/remote rigs)
- Low bandwidth (<1 kbps)
- Memory channels sync across network
- Can run multiple instances (e.g., for multi-radio)
- Logging integration with fldigi, WSJT-X, etc.

---

#### 6. Running WSJT-X in Parallel (FT8 + Waterfall)

**WSJT-X can run alongside your CW setup** for FT8/FT4 operation and spectrum waterfall display.

**Why add WSJT-X:**
- **Waterfall display** - Visual spectrum analyzer (see band activity)
- **FT8/FT4 capability** - Digital modes when not doing CW
- **Built-in CAT control** - Can share rigctld with flrig
- **Dual mode operation** - Switch between CW and FT8 without reconfiguration

**Installation:**

```bash
# Ubuntu/Debian
sudo apt install wsjtx

# Fedora
sudo dnf install wsjtx

# Or download latest from:
# https://physics.princeton.edu/pulsar/k1jt/wsjtx.html
```

**Configuration for Remote Operation:**

1. **File → Settings → Radio tab:**
   - **CAT Control:**
     - Rig: `Hamlib NET rigctl`
     - Network Server: `100.64.0.5:4532` (your rigctld address)
     - Poll Interval: 1000ms (1 second)
   
2. **Audio tab (CRITICAL for 2-way USB audio):**
   
   **Input (RX - for decoding):**
   - **Method 1 - PulseAudio Monitor** (Recommended, easiest):
     - Select: `Monitor of Built-in Audio Analog Stereo`
     - This captures QMX+ RX audio that JackTrip outputs to your speakers
     - Automatically works, no extra config
   
   **Output (TX - for transmitting FT8):**
   - **Select your sound card output**: `Built-in Audio Analog Stereo` (or hw:0,0)
   - WSJT-X will generate FT8 audio tones here
     - JackTrip captures this output via `-I hw:0,0`
     - Sends to remote QMX+ for transmission
   
   **Important: Use the SAME device for:**
   - JackTrip input (`-I hw:0,0`)
   - WSJT-X output (audio tab)
   - This creates the TX audio path: WSJT-X → Sound Card → JackTrip → QMX+

3. **PTT Method:**
   - **CAT** (via Hamlib) - Recommended, most reliable
     - WSJT-X sends PTT command via rigctld
     - QMX+ switches to TX mode
     - Then FT8 audio flows from WSJT-X → QMX+
   - **VOX** - Alternative (if CAT PTT has issues)
     - QMX+ VOX detects FT8 audio and keys up
     - Set VOX delay appropriately (100-200ms)
   - **DTR/RTS** - Not applicable for network rigctld

**Running Both flrig and WSJT-X:**

```bash
# Both can share the same rigctld connection!
# No conflict - they just poll for frequency/mode

# Start flrig for general rig control
flrig &

# Start WSJT-X for FT8 + waterfall
wsjtx &
```

**Typical Workflow:**

```
1. Start remote station (rigctld + CW receiver + JackTrip)
2. Start local flrig - monitor frequency, change bands
3. Start local WSJT-X - see waterfall, work FT8 stations
4. Use CW key for CW QSOs
5. Use WSJT-X for FT8 QSOs
6. Both share same radio via rigctld
```

**Audio Routing for WSJT-X:**

```
QMX+ RX Audio → JackTrip → Local PC Audio Output
                              ↓
                         ┌─────────────┐
                         ↓             ↓
                   Your Speakers    WSJT-X Input
                   (monitoring)     (decoding)
```

**Use ALSA loopback or PulseAudio monitoring:**

```bash
# Option 1: PulseAudio monitor (Linux)
# WSJT-X Audio Input: "Monitor of <your output device>"

# Option 2: JACK audio routing (more complex but flexible)
sudo apt install qjackctl
# Use JACK patchbay to route audio

# Option 3: Simple - just select same device
# Both you and WSJT-X listen to JackTrip output
```

**Waterfall Benefits:**
- See CW signals visually (helps find stations)
- Monitor band activity while operating
- Spot DX openings
- Check your signal quality (if remote has TX feedback)

**Bandwidth Impact:**

Adding WSJT-X doesn't increase network bandwidth significantly:
- WSJT-X uses existing audio stream (JackTrip)
- CAT polling minimal (<1 kbps)
- **Total impact: ~0 kbps** (uses existing connections)

**Updated Launcher with WSJT-X:**

```bash
#!/bin/bash
# Local Station Launcher with flrig + WSJT-X

REMOTE_IP="100.64.0.5"

echo "Connecting to Remote Station at $REMOTE_IP..."

# 1. Start CW sender
echo "Starting CW sender..."
cd ~/cw-protocol
python3 cw_usb_key_sender_tcp_ts.py $REMOTE_IP &
CW_PID=$!

# 2. Start JackTrip client
echo "Starting JackTrip audio..."
jacktrip -c $REMOTE_IP -q 4 --udprt &
JACKTRIP_PID=$!

# Wait for audio to stabilize
sleep 2

# 3. Start flrig GUI
echo "Starting flrig GUI..."
flrig &
FLRIG_PID=$!

# 4. Start WSJT-X (optional)
if [ "$1" = "--ft8" ]; then
    echo "Starting WSJT-X for FT8/waterfall..."
    wsjtx &
    WSJTX_PID=$!
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Local Station Connected!"
echo "═══════════════════════════════════════════"
echo "  Remote: $REMOTE_IP"
echo "  CW: Active (physical key)"
echo "  Audio: Active (JackTrip)"
echo "  Rig Control: flrig"
if [ "$1" = "--ft8" ]; then
    echo "  FT8/Waterfall: WSJT-X"
fi
echo "═══════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to disconnect"

trap "kill $CW_PID $JACKTRIP_PID $FLRIG_PID $WSJTX_PID 2>/dev/null; exit" INT
wait
```

**Usage:**
```bash
# CW only
./local-station.sh

# CW + FT8 + waterfall
./local-station.sh --ft8
```

**WSJT-X CAT Integration Notes:**

- **Frequency follows mode:** WSJT-X will QSY for FT8 calling frequencies
- **Mode switching:** WSJT-X sets mode to DATA/USB automatically
- **Manual override:** Use flrig to override WSJT-X frequency changes
- **Split operation:** WSJT-X can use VFO split (A/B)
- **No conflicts:** Both apps poll rigctld independently

**Best Practice:**

1. Use **flrig** for general band changes and monitoring
2. Use **WSJT-X** when you want FT8 or waterfall display
3. Use **CW key** for CW operation (always available)
4. All three can run simultaneously without conflict
wsjtx &
```

**Typical Workflow:**

```
1. Start remote station (rigctld + CW receiver + JackTrip)
2. Start local flrig - monitor frequency, change bands
3. Start local WSJT-X - see waterfall, work FT8 stations
4. Use CW key for CW QSOs
5. Use WSJT-X for FT8 QSOs
6. Both share same radio via rigctld
```

**Audio Routing for WSJT-X:**

```
QMX+ RX Audio → JackTrip → Local PC Audio Output
                              ↓
                         ┌─────────────┐
                         ↓             ↓
                   Your Speakers    WSJT-X Input
                   (monitoring)     (decoding)
```

**Use ALSA loopback or PulseAudio monitoring:**

```bash
# Option 1: PulseAudio monitor (Linux)
# WSJT-X Audio Input: "Monitor of <your output device>"

# Option 2: JACK audio routing (more complex but flexible)
sudo apt install qjackctl
# Use JACK patchbay to route audio

# Option 3: Simple - just select same device
# Both you and WSJT-X listen to JackTrip output
```

**Waterfall Benefits:**
- See CW signals visually (helps find stations)
- Monitor band activity while operating
- Spot DX openings
- Check your signal quality (if remote has TX feedback)

**Bandwidth Impact:**

Adding WSJT-X doesn't increase network bandwidth significantly:
- WSJT-X uses existing audio stream (JackTrip)
- CAT polling minimal (<1 kbps)
- **Total impact: ~0 kbps** (uses existing connections)

**Updated Launcher with WSJT-X:**

```bash
#!/bin/bash
# Local Station Launcher with flrig + WSJT-X

REMOTE_IP="100.64.0.5"

echo "Connecting to Remote Station at $REMOTE_IP..."

# 1. Start CW sender
echo "Starting CW sender..."
cd ~/cw-protocol
python3 cw_usb_key_sender_tcp_ts.py $REMOTE_IP &
CW_PID=$!

# 2. Start JackTrip client
echo "Starting JackTrip audio..."
jacktrip -c $REMOTE_IP -q 4 --udprt &
JACKTRIP_PID=$!

# Wait for audio to stabilize
sleep 2

# 3. Start flrig GUI
echo "Starting flrig GUI..."
flrig &
FLRIG_PID=$!

# 4. Start WSJT-X (optional)
if [ "$1" = "--ft8" ]; then
    echo "Starting WSJT-X for FT8/waterfall..."
    wsjtx &
    WSJTX_PID=$!
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Local Station Connected!"
echo "═══════════════════════════════════════════"
echo "  Remote: $REMOTE_IP"
echo "  CW: Active (physical key)"
echo "  Audio: Active (JackTrip)"
echo "  Rig Control: flrig"
if [ "$1" = "--ft8" ]; then
    echo "  FT8/Waterfall: WSJT-X"
fi
echo "═══════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to disconnect"

trap "kill $CW_PID $JACKTRIP_PID $FLRIG_PID $WSJTX_PID 2>/dev/null; exit" INT
wait
```

**Usage:**
```bash
# CW only
./local-station.sh

# CW + FT8 + waterfall
./local-station.sh --ft8
```

**WSJT-X CAT Integration Notes:**

- **Frequency follows mode:** WSJT-X will QSY for FT8 calling frequencies
- **Mode switching:** WSJT-X sets mode to DATA/USB automatically
- **Manual override:** Use flrig to override WSJT-X frequency changes
- **Split operation:** WSJT-X can use VFO split (A/B)
- **No conflicts:** Both apps poll rigctld independently

**Best Practice:**

1. Use **flrig** for general band changes and monitoring
2. Use **WSJT-X** when you want FT8 or waterfall display
3. Use **CW key** for CW operation (always available)
4. All three can run simultaneously without conflict

**Integration in launcher script:**

```bash
#!/bin/bash
# Local Station Launcher with flrig

REMOTE_IP="100.64.0.5"

echo "Connecting to Remote Station at $REMOTE_IP..."

# 1. Start CW sender (USB key)
echo "Starting CW sender..."
cd ~/cw-protocol
python3 cw_usb_key_sender_tcp_ts.py $REMOTE_IP &
CW_PID=$!

# 2. Start JackTrip client (audio)
echo "Starting JackTrip audio..."
jacktrip -c $REMOTE_IP -q 4 --udprt &
JACKTRIP_PID=$!

# 3. Start flrig GUI
echo "Starting flrig GUI..."
flrig &
FLRIG_PID=$!

echo ""
echo "═══════════════════════════════════════════"
echo "  Local Station Connected!"
echo "═══════════════════════════════════════════"
echo "  Remote: $REMOTE_IP"
echo "  CW: Active"
echo "  Audio: Active"
echo "  GUI: flrig (configure: 100.64.0.5:4532)"
echo "═══════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to disconnect"

trap "kill $CW_PID $JACKTRIP_PID $FLRIG_PID; exit" INT
wait
```

**flrig Configuration File** (`~/.flrig/flrig.prefs`):

```xml
<?xml version="1.0"?>
<FLRIG>
  <RIG>
    <XCVR>Hamlib NET rigctl</XCVR>
    <DEVICE>100.64.0.5:4532</DEVICE>
    <POLL_FREQUENCY>200</POLL_FREQUENCY>
    <POLL_SMETER>500</POLL_SMETER>
    <POLL_PTT>100</POLL_PTT>
  </RIG>
</FLRIG>
```

---

## Operational Usage

### Starting a Session

**Remote side:**
```bash
# If not auto-starting:
~/remote-station.sh
```

**Local side:**
```bash
# Connect
~/local-station.sh

# In another terminal - change frequency
rigctl -m 2 -r 100.64.0.5:4532
Rig command: F 14060000
Rig command: M CW 500
```

**Now operate normally:**
- Key is connected via USB → CW keying works
- Audio flows automatically → hear QSOs
- Use rigctl for band changes

### Latency Budget

Total system latency (local key press → remote radio TX):

```
Component              Latency      Cumulative
──────────────────────────────────────────────
USB key detection      ~5ms         5ms
Protocol encoding      ~2ms         7ms
Network transmission   ~20-50ms     27-57ms
Jitter buffer          100-150ms    127-207ms
GPIO output            ~1ms         128-208ms
QMX+ keying response   ~5-10ms      133-218ms
──────────────────────────────────────────────
TOTAL:                              130-220ms
```

**Perceived latency**: ~150-200ms typical (acceptable for QSO, contests challenging)

---

## Troubleshooting

### CW Protocol Issues

**Problem**: Connection refused on port 7356

**Solution**: 
```bash
# Check receiver is running
sudo netstat -tlnp | grep 7356

# Check firewall
sudo ufw status
sudo ufw allow 7356/tcp
```

**Problem**: High jitter, unstable timing

**Solution**: Increase jitter buffer
```bash
python3 cw_gpio_output_tcp_ts.py --jitter-buffer 200
```

---

### Hamlib Issues

**Problem**: `rigctld: rig_open: error = IO error`

**Solution**: Check USB connection and permissions
```bash
# Find device
ls -l /dev/ttyUSB*

# Add user to dialout group
sudo usermod -a -G dialout $USER
# Log out and back in

# Test manually
rigctl -m 2049 -r /dev/ttyUSB0 -s 38400
```

**Problem**: Commands slow or timing out

**Solution**: Check network and increase timeout
```bash
rigctl -m 2 -r 100.64.0.5:4532 --timeout=5000
```

---

### Audio Issues

#### Testing Audio Path: Server to Client

**Before troubleshooting complex issues, verify the basic audio path works.**

##### Complete Working Test Procedure ✅

**This test verifies JackTrip audio routing works without QMX+ hardware.**

**Server (Raspberry Pi) setup:**

```bash
# 1. Clean slate - stop everything
killall jackd jacktrip jack_metro 2>/dev/null
sleep 2

# 2. Start JACK with dummy device (no hardware needed for test)
jackd -d dummy -r 48000 -p 128 &
sleep 3

# 3. Start JackTrip server
jacktrip -s -q 4 --udprt &
sleep 2

# 4. Verify JACK ports exist
jack_lsp
# Should show:
#   system:capture_1
#   system:capture_2
#   system:playback_1
#   system:playback_2
#   JackTrip:send_1
#   JackTrip:send_2
#   JackTrip:receive_1
#   JackTrip:receive_2

# 5. Install JACK example tools if needed
sudo apt install jack-example-tools

# 6. Start metronome (generates test audio clicks)
jack_metro -b 120 &
sleep 1

# 7. Find the actual metro port name
jack_lsp | grep metro
# Will show: metro:120_bpm (NOT metro:60_bpm!)
# Port name reflects the BPM setting

# 8. Connect metronome to JackTrip send ports
jack_connect metro:120_bpm JackTrip:send_1
jack_connect metro:120_bpm JackTrip:send_2

# 9. Verify connections
jack_lsp -c
# Should show:
#   metro:120_bpm
#      JackTrip:send_1
#      JackTrip:send_2

echo "✅ Server ready - audio is flowing to JackTrip!"
echo "   Start CLIENT now and listen for metronome clicks"
```

**⚠️ Important: Metronome Port Names**

The metronome port name reflects the BPM you specified:
- `jack_metro -b 60` creates port `metro:60_bpm`
- `jack_metro -b 120` creates port `metro:120_bpm`
- `jack_metro -b 240` creates port `metro:240_bpm`

**Always check with `jack_lsp | grep metro` before connecting!**

**Client (Fedora/PipeWire) setup:**

```bash
# 1. Set HDMI/correct speakers as default output
wpctl status | grep -A10 "Sinks:"
# Find your speaker output ID (e.g., HDMI/DisplayPort or analog)

# Set as default (replace XX with your sink ID)
wpctl set-default XX

# Set volume to 100%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 100%

# 2. Verify speakers work
speaker-test -c 2 -t sine -f 700
# Should hear 700Hz tone from your speakers
# If silent: Check monitor/speaker volume buttons!

# 3. Connect JackTrip client
jacktrip -c 192.168.1.201 -q 4 --udprt -R

# You should see:
#   "Setting Up RtAudio Interface"
#   "Waiting for Peer..."
#   "Received Connection from Peer!"

# 4. ✅ Listen for metronome clicks from your speakers!
#    You should hear: Click... Click... Click... (120 BPM)
```

**Expected Result:**

✅ **Success**: You hear regular metronome clicks (120 BPM) from speakers  
✅ **Audio path verified**: JACK → JackTrip → Network → Client → Speakers  
✅ **JackTrip routing works**: Problem is NOT with JackTrip  

If you hear the clicks, the complete chain works:
- JACK audio routing ✓
- JackTrip encoding/decoding ✓
- Network transmission ✓
- Client audio output ✓

**Next step:** The issue is QMX+ not sending audio to USB, not JackTrip configuration.

---

#### Auto-Starting Audio Server on Raspberry Pi

**You ARE running "real JACK" on Raspberry Pi!** The issue is making it auto-start reliably.

**Solution: Systemd service with automatic restart**

**Create `/etc/systemd/system/remote-audio.service`:**

```bash
sudo nano /etc/systemd/system/remote-audio.service
```

**Add this configuration:**

```ini
[Unit]
Description=Remote Audio Server (JACK + JackTrip)
After=network.target sound.target
Wants=network.target

[Service]
Type=forking
User=tomas
WorkingDirectory=/home/tomas

# Stop any existing instances first
ExecStartPre=/usr/bin/killall -q jackd jacktrip || true
ExecStartPre=/bin/sleep 2

# Start JACK daemon
ExecStart=/usr/bin/jackd -d alsa -d hw:3,0 -r 48000 -p 256 -v

# Start JackTrip after JACK is ready (using separate service)
ExecStartPost=/bin/sleep 3
ExecStartPost=/usr/bin/systemctl start jacktrip.service

# Restart on failure
Restart=on-failure
RestartSec=10

# Cleanup on stop
ExecStop=/usr/bin/killall jackd

[Install]
WantedBy=multi-user.target
```

**Create `/etc/systemd/system/jacktrip.service`:**

```bash
sudo nano /etc/systemd/system/jacktrip.service
```

```ini
[Unit]
Description=JackTrip Audio Streaming Server
After=remote-audio.service
Requires=remote-audio.service
PartOf=remote-audio.service

[Service]
Type=simple
User=tomas

# Start JackTrip server
ExecStart=/usr/bin/jacktrip -s -q 16 --udprt

# Restart on failure
Restart=on-failure
RestartSec=5

# Cleanup
ExecStop=/usr/bin/killall jacktrip

[Install]
WantedBy=multi-user.target
```

**Enable and start the services:**

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start at boot
sudo systemctl enable remote-audio.service

# Start now
sudo systemctl start remote-audio.service

# Check status
sudo systemctl status remote-audio.service
sudo systemctl status jacktrip.service

# View logs
journalctl -u remote-audio.service -f
journalctl -u jacktrip.service -f
```

**Benefits:**
- ✅ Auto-starts at boot
- ✅ Auto-restarts if crashes
- ✅ Proper dependency management (JackTrip waits for JACK)
- ✅ Clean shutdown
- ✅ System logs for debugging

**Manual control commands:**

```bash
# Stop services
sudo systemctl stop remote-audio.service

# Start services
sudo systemctl start remote-audio.service

# Restart services
sudo systemctl restart remote-audio.service

# Disable auto-start
sudo systemctl disable remote-audio.service

# Check if running
sudo systemctl is-active remote-audio.service
```

**Monitoring:**

```bash
# Watch logs in real-time
journalctl -u remote-audio.service -u jacktrip.service -f

# Check recent failures
journalctl -u remote-audio.service --since "1 hour ago" | grep -i error

# List all restarts
systemctl list-units --state=failed
```

**Troubleshooting systemd service:**

```bash
# If JACK fails to start, check audio device
aplay -l

# Update hw:3,0 in service file if needed
sudo nano /etc/systemd/system/remote-audio.service
# Change: ExecStart=/usr/bin/jackd -d alsa -d hw:X,0 ...

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart remote-audio.service
```

---

#### Audio Routing Issues on Fedora/PipeWire Systems

**Fedora uses PipeWire by default** - not plain JACK or PulseAudio. This affects JackTrip routing.

**Problem**: Audio routing to wrong device (HDMI instead of desired speakers)

**Diagnosis - List all audio sinks:**

```bash
# Method 1: PipeWire native command
wpctl status

# Look for section "Audio" → "Sinks:"
# Example output:
# │  ├─ Sinks:
# │  │      42. Ryzen HD Audio Controller Digital Microphone
# │  │      73. Renoir/Cezanne HDMI/DP Audio Controller HDMI / DisplayPort 1 Output [vol: 0.32]
# │  │  *   81. Vardagsrum                    [vol: 1.00]
#            ^^^ Asterisk (*) marks default sink

# Method 2: PulseAudio compatibility
pactl list sinks short

# Example output:
# 73  alsa_output.pci-0000_06_00.1.hdmi-stereo-extra1  ...  RUNNING
# 81  alsa_output.pci-0000_06_00.6.analog-stereo      ...  RUNNING
```

**Identify your speakers:**
- Look for names like: `analog-stereo`, `ALC897`, or custom names
- HDMI outputs have names like: `hdmi-stereo`, `DisplayPort`
- **Note**: Some monitors (like DELL U3415W) have built-in speakers via HDMI and this IS the correct output

**Solution 1: Set Correct Default Sink**

```bash
# Find your speakers' sink ID from wpctl status (e.g., 81)
wpctl set-default 81

# Or using PulseAudio compatibility:
pactl set-default-sink alsa_output.pci-0000_06_00.6.analog-stereo

# Verify change
wpctl status | grep -A5 "Sinks:"
# Should show * next to your speakers now

# Test audio immediately
speaker-test -c 2

# Restart JackTrip for it to use new default
killall jacktrip
jacktrip -c 192.168.1.201 -q 4 --udprt -R

# Audio should now come from correct speakers!
```

**Solution 2: GUI Tools for Visual Routing**

**Option A: Helvum (Modern PipeWire Graph Editor)**

```bash
# Install
sudo dnf install helvum

# Run
helvum &

# In GUI:
# 1. Find "ALSA Playback [jacktrip]" on left
# 2. Find your speakers on right
# 3. Drag connection line between them
# 4. Audio instantly routes correctly!
```

**Option B: pavucontrol (Simple, PulseAudio-compatible)**

```bash
# Install
sudo dnf install pavucontrol

# Run
pavucontrol &

# Go to "Playback" tab while JackTrip is running
# Find "ALSA plug-in [jacktrip]"
# Change output device dropdown to your speakers
# Instant fix!
```

**Make Default Sink Permanent**

```bash
# Create PipeWire user config
mkdir -p ~/.config/pipewire/pipewire.conf.d

# Set default sink permanently
cat > ~/.config/pipewire/pipewire.conf.d/default-audio.conf << 'EOF'
context.properties = {
    # Use device name from 'pactl list sinks short'
    default.audio.sink = "alsa_output.pci-0000_06_00.6.analog-stereo"
}
EOF

# Restart PipeWire to apply
systemctl --user restart pipewire pipewire-pulse

# Verify
wpctl status
# Should show your speakers as default now
```

---

#### QMX+ USB Audio Issues

**Problem**: QMX+ USB audio device not appearing

**Solution**: Check Linux service conflicts
```bash
# 1. Check and disable ModemManager (CRITICAL!)
sudo systemctl status ModemManager
sudo systemctl mask ModemManager

# 2. Check and disable BRLTTY
sudo systemctl status brltty
sudo systemctl mask brltty

# 3. Disconnect and reconnect QMX+ USB

# 4. Verify USB device detected
lsusb | grep -i "QRP\|QMX"
dmesg | tail -20

# 5. Check USB audio enabled on QMX+ menu
# Look for: Settings → USB → Audio Enable

# 6. Verify audio device appears
aplay -l | grep -i "QMX\|Transceiver"
```

**Problem**: `arecord` fails with "Sample format non available"

**Solution**: QMX+ requires 24-bit audio format
```bash
# WRONG (won't work):
arecord -D hw:3,0 -f S16_LE -r 48000 -c 2 -d 5 test.wav

# CORRECT (24-bit format):
arecord -D hw:3,0 -f S24_3LE -r 48000 -c 2 -d 5 test.wav
```

**Problem**: QMX+ recording is silent (no audio data)

**Solution**: Check QMX+ audio output settings
```bash
# 1. Tune QMX+ to active frequency (important!)
echo "F 14060000" | rigctl -m 2052 -r localhost:4532
echo "M CW 500" | rigctl -m 2052 -r localhost:4532

# 2. Check QMX+ volume (on radio front panel)
#    - Not muted
#    - Set to reasonable level (50-70%)

# 3. Verify USB audio enabled in QMX+ menu
#    - Settings → USB → Audio = Enabled

# 4. Check ALSA mixer levels
alsamixer
# Press F6, select QMX+ device (card 3)
# Ensure Mic/Capture level is 70-90%

# 5. Or via command line:
amixer -c 3 sset 'Mic',0 80%
amixer -c 3 sset 'Capture',0 80%
```

**Problem**: No audio with JackTrip

**Solution**: Check JACK is running and connected
```bash
# 1. Check JACK daemon is running
ps aux | grep jackd

# 2. List JACK ports
jack_lsp

# 3. Check connections
jack_lsp -c
# Should show system:capture → JackTrip:send
#          and JackTrip:receive → system:playback

# 4. If JACK not running, start it:
jackd -d alsa -d hw:3,0 -r 48000 -p 128 &

# 5. Restart JackTrip
jacktrip -s -q 4 --udprt
```

**Problem**: JackTrip shows error about `-I` or `-O` options

**Solution**: These options don't exist in JACK-only builds
```bash
# Don't use (wrong for v2.5.x):
jacktrip -s -q 4 --udprt -I hw:3,0 -O hw:3,0

# Use JACK for device selection instead:
jackd -d alsa -d hw:3,0 -r 48000 -p 128 &
jacktrip -s -q 4 --udprt
```

**Problem**: Audio dropouts or glitches

**Solution**: Increase buffer size
```bash
# Increase queue buffer
jacktrip -c <ip> -q 16  # Larger buffer for stability
```

**Problem**: "'default' server already active" after QMX+ power cycle

**Symptoms**: 
- QMX+ turned off and back on
- JACK won't restart
- Error: "Failed to open server"

**Solution**: Properly restart JACK and services
```bash
# 1. Kill all existing JACK and JackTrip processes
killall -9 jackd jackdmp jacktrip
sleep 2

# 2. Verify QMX+ USB device reappeared
lsusb | grep -i QRP
aplay -l | grep -i QMX

# 3. Wait if device not ready yet
if ! aplay -l | grep -q "card 3"; then
    echo "Waiting for QMX+ to appear..."
    sleep 5
fi

# 4. Restart JACK with QMX+ device
jackd -d alsa -d hw:3,0 -r 48000 -p 256 &
sleep 3

# 5. Verify JACK started successfully
if jack_lsp > /dev/null 2>&1; then
    echo "JACK running"
else
    echo "JACK failed to start!"
    exit 1
fi

# 6. Restart JackTrip server
jacktrip -s -q 16 --udprt &

# 7. Verify connections
jack_lsp -c
```

**Quick restart script for server:**
```bash
#!/bin/bash
# restart-audio.sh - Quick restart after QMX+ power cycle

echo "Stopping services..."
killall -9 jackd jackdmp jacktrip rigctld 2>/dev/null
sleep 2

echo "Waiting for QMX+ USB device..."
for i in {1..10}; do
    if aplay -l | grep -q "card 3"; then
        echo "QMX+ found!"
        break
    fi
    echo "Waiting... ($i/10)"
    sleep 2
done

if ! aplay -l | grep -q "card 3"; then
    echo "ERROR: QMX+ not found after 20 seconds"
    echo "Check USB connection and power"
    exit 1
fi

echo "Starting JACK..."
jackd -d alsa -d hw:3,0 -r 48000 -p 256 &
sleep 3

if ! jack_lsp > /dev/null 2>&1; then
    echo "ERROR: JACK failed to start"
    exit 1
fi

echo "Starting JackTrip..."
jacktrip -s -q 16 --udprt &
sleep 2

echo "Starting rigctld..."
rigctld -m 2057 -r /dev/ttyACM0 -s 115200 -t 4532 &
sleep 1

echo ""
echo "✅ All services restarted!"
echo ""
jack_lsp -c | head -20
```

**Save as `~/restart-audio.sh` and use:**
```bash
chmod +x ~/restart-audio.sh

# Run after QMX+ power cycle
~/restart-audio.sh
```

**If using systemd services:**
```bash
# Restart everything properly
sudo systemctl restart remote-audio.service

# Check status
sudo systemctl status remote-audio.service
sudo systemctl status jacktrip.service

# View logs if there are issues
journalctl -u remote-audio.service -n 50
```

**Problem**: High latency (>100ms audio delay)

**Solution**: Reduce buffer, check network
```bash
# Try smaller buffer (only if network is perfect)
jacktrip -c <ip> -q 8

# Check network latency
ping <remote-ip>
```

**Problem**: "'default' server already active" when restarting JACK

**Cause**: Old JACK server still running (especially after QMX+ power cycle)

**Solution**: Force kill all JACK processes before restarting
```bash
# Kill all JACK processes INCLUDING PulseAudio conflicts
sudo killall -9 jackd jackdmp jacktrip pulseaudio
sleep 2

# Verify they're gone
ps aux | grep jack

# Wait for QMX+ to reappear if it was power cycled
aplay -l | grep -i QMX
# If not found, wait a few seconds and try again

# Restart JACK with realtime priority and stability flags
JACK_NO_AUDIO_RESERVATION=1 jackd -R -d alsa -d hw:3,0 -r 48000 -p 256 -n 3 &
sleep 5

# Restart JackTrip
jacktrip -s -q 16 --udprt &
```

**Problem**: JACK crashing, xruns, or audio dropouts

**Solution**: Verify JACK can access the device and apply stability settings

1. **Verify the QMX+ USB device is visible**:
   ```bash
   arecord -l | grep -i QMX
   # Should show: card 3: Device [QMX+ USB Audio Device], device 0
   ```

2. **Kill all audio processes that might conflict**:
   ```bash
   sudo killall -9 pulseaudio jackd jackdmp jacktrip
   ```

3. **Start JACK with realtime priority and proper flags**:
   ```bash
   # Use these flags for maximum stability:
   # - JACK_NO_AUDIO_RESERVATION=1: Bypass PulseAudio audio reservation
   # - -R: Enable realtime scheduling (requires permissions)
   # - -n 3: More period retries before xrun
   
   JACK_NO_AUDIO_RESERVATION=1 jackd -R -d alsa -d hw:3,0 -r 48000 -p 256 -n 3 &
   sleep 5  # Wait longer for JACK to fully initialize
   ```

4. **Test audio capture is working**:
   ```bash
   # This should play noise/silence through HDMI speakers
   speaker-test -t wav -c 2
   # Press Ctrl+C to stop after confirming audio works
   ```

5. **Check for xruns (buffer underruns)**:
   ```bash
   # JACK will print xrun messages if buffers are too small
   # If you see frequent xruns, increase -p 256 to -p 512
   ```

6. **Verify realtime permissions** (if -R flag fails):
   ```bash
   # Check if user is in 'audio' group
   groups | grep audio
   
   # If not, add user to audio group:
   sudo usermod -aG audio $USER
   # Then logout and login again
   
   # Check realtime limits
   ulimit -r  # Should be >0, preferably unlimited
   ```

7. **Disable onboard audio** (prevents conflicts on Raspberry Pi):
   ```bash
   # Edit boot config
   sudo nano /boot/config.txt
   
   # Add this line:
   dtparam=audio=off
   
   # Save and reboot
   sudo reboot
   ```

---

### Network Issues

**Problem**: Can't connect through Tailscale

**Solution**: Check Tailscale status
```bash
tailscale status
sudo tailscale up  # Restart if down

# Test connectivity
ping $(tailscale ip -4 <remote-hostname>)
```

**Problem**: UDP packets not reaching destination

**Solution**: Check router and firewall
```bash
# Test with netcat
# Remote:
nc -u -l 4464

# Local:
echo "test" | nc -u <remote-ip> 4464

# If fails, check router port forwarding
```

**Problem**: High packet loss on audio

**Solution**: 
```bash
# Check with ping
ping -c 100 <remote-ip> | grep loss

# If >2% loss, consider:
# 1. Use FEC in JackTrip: jacktrip -s -r
# 2. Switch to TCP-based audio (higher latency)
# 3. Check ISP connection quality
```

---

## Performance Benchmarks

### Expected Performance

**LAN (Local Network):**
- CW latency: 50-80ms
- Audio latency: 5-15ms
- Hamlib response: 10-20ms
- Packet loss: 0%

**Good Internet (<50ms ping):**
- CW latency: 120-180ms
- Audio latency: 20-40ms
- Hamlib response: 30-60ms
- Packet loss: <0.5%

**Poor Internet (>100ms ping):**
- CW latency: 200-300ms
- Audio latency: 50-100ms
- Hamlib response: 100-200ms
- Packet loss: 1-5%

### Bandwidth Usage

```
Service              Bandwidth      Data Rate
─────────────────────────────────────────────
CW Protocol (active) 2-3 kbps       ~1 MB/hour
Hamlib (commands)    <1 kbps        ~0.5 MB/hour
JackTrip (Opus)      48 kbps        ~20 MB/hour
JackTrip (raw)       350 kbps       ~150 MB/hour
─────────────────────────────────────────────
Total (Opus):        ~50 kbps       ~22 MB/hour
```

---

## Advanced Topics

### PTT Integration

Currently CW protocol and Hamlib PTT are separate. To integrate:

**Option 1: GPIO PTT (Simplest)**
- Add second GPIO output on remote RPi
- Connect to QMX+ PTT input (separate from key)
- CW protocol controls PTT automatically

**Option 2: Hamlib PTT via Script**
```bash
# Wrapper script that calls rigctl
#!/bin/bash
# ptt-on.sh
echo "T 1" | rigctl -m 2 -r localhost:4532

# ptt-off.sh
echo "T 0" | rigctl -m 2 -r localhost:4532
```

**Option 3: Modify cw_gpio_output_tcp_ts.py**
```python
# Add Hamlib control
import subprocess

def set_ptt(state):
    cmd = f"echo 'T {1 if state else 0}' | rigctl -m 2 -r localhost:4532"
    subprocess.run(cmd, shell=True)

# In GPIO output callback:
if key_down:
    set_ptt(True)  # PTT on first key-down
```

### Audio Recording

Record QSOs using GStreamer:

```bash
# Record remote audio to file
gst-launch-1.0 udpsrc port=5004 caps="application/x-rtp" ! \
  rtpopusdepay ! opusdec ! \
  audioconvert ! audioresample ! \
  vorbisenc ! oggmux ! \
  filesink location=qso-$(date +%Y%m%d-%H%M).ogg
```

### Multiple Operators

Hamlib and CW protocol support only one connection at a time. For multiple operators:

1. **Time-sharing**: Coordinate via voice/chat
2. **Queue system**: Add connection queue in launcher script
3. **Separate radios**: Each operator gets dedicated remote station

---

## Security Considerations

### Network Security

**Without VPN (port forwarding):**
- Exposed ports: 7356, 4532, 4464
- No encryption by default
- Firewall rules critical
- Consider using SSH tunnels

**With Tailscale:**
- All traffic encrypted (WireGuard)
- No exposed public ports
- Only authenticated devices can connect
- Recommended for internet operation

### SSH Tunnels (Alternative to VPN)

```bash
# Forward all ports through SSH
ssh -L 7356:localhost:7356 \
    -L 4532:localhost:4532 \
    -L 4464:localhost:4464 \
    pi@remote-ip

# Then connect to localhost instead
python3 cw_usb_key_sender_tcp_ts.py localhost
rigctl -m 2 -r localhost:4532
```

---

## References

- **Hamlib**: https://github.com/Hamlib/Hamlib
- **flrig**: https://github.com/w1hkj/flrig (Rig control GUI)
- **JackTrip**: https://github.com/jacktrip/jacktrip
- **Tailscale**: https://tailscale.com
- **QMX+ Manual**: https://qrp-labs.com/qmx/manual.html
- **CW Protocol Specification**: [CW_PROTOCOL_SPECIFICATION.md](CW_PROTOCOL_SPECIFICATION.md)

---

## Summary

This architecture provides **professional-grade remote radio operation** by:

✅ **Preserving operator timing** - Duration-encoded CW protocol  
✅ **Full rig control** - Hamlib integration with GUI (flrig)  
✅ **Audio monitoring** - Low-latency P2P streaming  
✅ **Network flexibility** - Port forwarding or Tailscale VPN  
✅ **Raspberry Pi compatible** - Cost-effective remote station  
✅ **Proven components** - Each system battle-tested  
✅ **User-friendly** - Graphical interface for rig control  
✅ **FT8/Digital modes capable** - 2-way audio via QMX+ USB sound card

Total latency (150-200ms typical) is acceptable for casual QSOs. Contest operation possible but requires practice to adapt to delay.

---

## Testing 2-Way Audio for FT8 Operation

**Before operating FT8, verify TX audio path is working:**

```bash
# On local PC - test TX audio path
# 1. Start JackTrip client with full duplex
jacktrip -c <remote-ip> -q 4 --udprt -I hw:0,0 -O hw:0,0

# 2. In another terminal, generate test tone
speaker-test -D hw:0,0 -c 1 -t sine -f 700

# 3. On remote RPi, monitor QMX+ USB input
arecord -D hw:1,0 -f S16_LE -r 48000 -c 1 -d 5 remote-test.wav
# Transfer file back and play it:
scp pi@remote-ip:remote-test.wav .
aplay remote-test.wav
# You should hear the 700Hz tone you generated!

# If you hear the tone, TX audio path is working!
# WSJT-X FT8 will use this same path
```

**WSJT-X Audio Configuration Summary for 2-Way Operation:**

| Setting | Value | Purpose |
|---------|-------|----------|
| **Input** | Monitor of Built-in Audio | Captures QMX+ RX for decoding |
| **Output** | Built-in Audio (hw:0,0) | Sends FT8 audio to JackTrip → QMX+ |
| **CAT Control** | Hamlib NET rigctl | PTT and frequency control |
| **PTT Method** | CAT | Reliable keying via rigctld |

**Troubleshooting 2-Way Audio:**

**Problem**: WSJT-X decodes incoming FT8 but doesn't transmit

**Solution**: Check audio output device
```bash
# Verify JackTrip is capturing from correct device
jacktrip -c <remote-ip> -q 4 --udprt -I hw:0,0 -O hw:0,0 --verbose

# WSJT-X Audio Output must match JackTrip input device
# Both should be: hw:0,0 (or your sound card)
```

**Problem**: TX audio distorted or clipping

**Solution**: Reduce WSJT-X audio level
- File → Settings → Audio
- Pwr slider: Start at 50% (10-20 watts typical for FT8)
- Monitor ALC on QMX+ display (should barely move)

**Problem**: Can't hear RX audio in WSJT-X waterfall

**Solution**: Check PulseAudio monitor
```bash
# List PulseAudio sources
pactl list sources | grep -i monitor

# In WSJT-X, select the monitor that matches your output device
```

---

*Document version 1.0 - December 2025*
