#!/bin/bash
# Quick Restart Script for Audio Server
# Use this after QMX+ power cycle or when JACK fails to start
# Version 1.0

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "═══════════════════════════════════════════"
echo "  Audio Server Restart"
echo "═══════════════════════════════════════════"
echo ""

# Step 1: Kill all existing processes (including PulseAudio conflicts)
echo -e "${YELLOW}⚠${NC} Stopping all audio services..."
sudo killall -9 jackd jackdmp jacktrip rigctld pulseaudio 2>/dev/null
sleep 2

# Verify they're stopped
if pgrep -x jackd > /dev/null || pgrep -x jacktrip > /dev/null; then
    echo -e "${RED}✗${NC} Some processes still running, trying again..."
    killall -9 jackd jackdmp jacktrip rigctld 2>/dev/null
    sleep 2
fi

echo -e "${GREEN}✓${NC} All services stopped"
echo ""

# Step 2: Wait for QMX+ USB device
echo "Waiting for QMX+ USB device..."
QMX_FOUND=0

for i in {1..10}; do
    if lsusb | grep -qi "QRP"; then
        QMX_FOUND=1
        echo -e "${GREEN}✓${NC} QMX+ USB detected"
        break
    fi
    echo "  Waiting... ($i/10)"
    sleep 2
done

if [ $QMX_FOUND -eq 0 ]; then
    echo -e "${RED}✗${NC} QMX+ USB not found after 20 seconds!"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check QMX+ is powered on"
    echo "  2. Check USB cable connection"
    echo "  3. Run: lsusb | grep -i QRP"
    echo "  4. Run: dmesg | tail -20"
    exit 1
fi

# Step 3: Wait for audio device
echo "Waiting for QMX+ audio device..."
AUDIO_FOUND=0
AUDIO_CARD=""

for i in {1..5}; do
    AUDIO_CARD=$(aplay -l 2>/dev/null | grep -i "QMX\|Transceiver" | grep -o "card [0-9]" | awk '{print $2}' | head -1)
    if [ -n "$AUDIO_CARD" ]; then
        AUDIO_FOUND=1
        echo -e "${GREEN}✓${NC} QMX+ audio found: hw:${AUDIO_CARD},0"
        break
    fi
    echo "  Waiting for audio device... ($i/5)"
    sleep 2
done

if [ $AUDIO_FOUND -eq 0 ]; then
    echo -e "${YELLOW}⚠${NC} QMX+ audio device not found!"
    echo ""
    echo "USB device detected but audio not ready. This may mean:"
    echo "  1. USB audio disabled in QMX+ menu (Settings → USB → Audio)"
    echo "  2. ModemManager interfering (run: sudo systemctl mask ModemManager)"
    echo "  3. Device needs more time to initialize"
    echo ""
    echo "Current audio devices:"
    aplay -l
    echo ""
    read -p "Use card number manually? (Enter card number or 'q' to quit): " MANUAL_CARD
    
    if [ "$MANUAL_CARD" = "q" ]; then
        exit 1
    fi
    
    if [[ "$MANUAL_CARD" =~ ^[0-9]+$ ]]; then
        AUDIO_CARD=$MANUAL_CARD
        echo -e "${GREEN}✓${NC} Using hw:${AUDIO_CARD},0"
    else
        echo -e "${RED}✗${NC} Invalid input"
        exit 1
    fi
fi

echo ""

# Step 4: Start JACK with realtime priority and better stability
echo "Starting JACK daemon with realtime priority..."
JACK_NO_AUDIO_RESERVATION=1 jackd -R -d alsa -d hw:${AUDIO_CARD},0 -r 48000 -p 256 -n 3 &
JACK_PID=$!
sleep 5

# Verify JACK started
if ! ps -p $JACK_PID > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} JACK failed to start!"
    echo ""
    echo "Common causes:"
    echo "  1. Audio device busy (check: fuser -v /dev/snd/*)"
    echo "  2. Wrong sample rate (QMX+ may only support 48kHz)"
    echo "  3. Permissions issue (check: groups | grep audio)"
    exit 1
fi

# Check JACK is responding
if ! jack_lsp > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} JACK started but not responding!"
    kill $JACK_PID 2>/dev/null
    exit 1
fi

echo -e "${GREEN}✓${NC} JACK running (PID: $JACK_PID)"
echo ""

# Step 5: Start JackTrip
echo "Starting JackTrip server..."
jacktrip -s -q 16 --udprt &
JACKTRIP_PID=$!
sleep 2

if ! ps -p $JACKTRIP_PID > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} JackTrip failed to start!"
    kill $JACK_PID 2>/dev/null
    exit 1
fi

echo -e "${GREEN}✓${NC} JackTrip server running (PID: $JACKTRIP_PID)"
echo ""

# Step 6: Start rigctld (optional but recommended)
echo "Starting rigctld..."

# Check for serial device
if [ -e "/dev/ttyACM0" ]; then
    rigctld -m 2057 -r /dev/ttyACM0 -s 115200 -t 4532 &
    RIGCTLD_PID=$!
    sleep 1
    
    if ps -p $RIGCTLD_PID > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} rigctld running (PID: $RIGCTLD_PID)"
    else
        echo -e "${YELLOW}⚠${NC} rigctld failed to start (non-critical)"
    fi
else
    echo -e "${YELLOW}⚠${NC} Serial device /dev/ttyACM0 not found, skipping rigctld"
fi

echo ""

# Step 7: Verify JACK connections
echo "JACK connections:"
jack_lsp -c | head -20

echo ""
echo "═══════════════════════════════════════════"
echo -e "  ${GREEN}✓${NC} Audio Server Restarted!"
echo "═══════════════════════════════════════════"
echo ""
echo "Services running:"
echo "  • JACK:     hw:${AUDIO_CARD},0 @ 48000Hz, buffer 256"
echo "  • JackTrip: UDP port 4464, queue 16"
if [ -n "$RIGCTLD_PID" ] && ps -p $RIGCTLD_PID > /dev/null 2>&1; then
    echo "  • rigctld:  TCP port 4532"
fi
echo ""
echo "Client connection:"
echo "  jacktrip -c $(hostname -I | awk '{print $1}') -q 16 --udprt -R"
echo ""
