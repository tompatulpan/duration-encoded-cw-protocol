#!/bin/bash
# Test P2P audio streaming between Raspberry Pi and local PC
# Usage: ./test-p2p-audio.sh

SERVER_IP="192.168.1.201"
SERVER_USER="tomas"

echo "========================================"
echo "P2P Audio Test"
echo "========================================"
echo ""

# Check local client status
echo "1. Checking local JackTrip client..."
if pgrep -f "jacktrip.*-c.*$SERVER_IP" > /dev/null; then
    echo "   ✓ JackTrip client is running"
    ps aux | grep -E "jacktrip.*-c.*$SERVER_IP" | grep -v grep | head -1
else
    echo "   ✗ JackTrip client NOT running"
    echo ""
    echo "   Start client with:"
    echo "   jacktrip -c $SERVER_IP -q 16 --udprt -R"
fi

echo ""
echo "2. Checking server status (requires SSH password)..."
ssh -o ConnectTimeout=5 $SERVER_USER@$SERVER_IP "bash -s" << 'ENDSSH'
    
    echo "   Server processes:"
    
    # Check JACK
    if pgrep jackd > /dev/null || pgrep jackdmp > /dev/null; then
        echo "   ✓ JACK is running"
        ps aux | grep -E "jackd" | grep -v grep | head -1
    else
        echo "   ✗ JACK NOT running"
        echo ""
        echo "   Start JACK with:"
        echo "   JACK_NO_AUDIO_RESERVATION=1 jackd -R -d alsa -d hw:3,0 -r 48000 -p 256 -n 3 &"
    fi
    
    # Check JackTrip server
    if pgrep -f "jacktrip.*-s" > /dev/null; then
        echo "   ✓ JackTrip server is running"
        ps aux | grep -E "jacktrip.*-s" | grep -v grep | head -1
    else
        echo "   ✗ JackTrip server NOT running"
        echo ""
        echo "   Start JackTrip server with:"
        echo "   jacktrip -s -q 16 --udprt &"
    fi
    
    echo ""
    echo "   JACK connections:"
    jack_lsp -c 2>/dev/null || echo "   (jack_lsp not available or JACK not running)"
    
ENDSSH

echo ""
echo "3. Testing audio path..."
echo ""
echo "   On the SERVER (RPi), run this test:"
echo "   ssh $SERVER_USER@$SERVER_IP"
echo "   jack_metro -b 120  # Should produce 120 BPM clicks"
echo ""
echo "   You should hear the metronome through your HDMI speakers on this PC."
echo ""
echo "4. Testing audio levels..."
echo "   On the SERVER, check capture level:"
echo "   ssh $SERVER_USER@$SERVER_IP 'amixer -c 3 sget Capture'"
echo ""
echo "========================================"
echo "Quick Commands:"
echo "========================================"
echo ""
echo "Start server (on RPi):"
echo "  ssh $SERVER_USER@$SERVER_IP"
echo "  ./restart-audio-server.sh"
echo ""
echo "Start client (on this PC):"
echo "  jacktrip -c $SERVER_IP -q 16 --udprt -R"
echo ""
echo "Test with metronome (on RPi):"
echo "  ssh $SERVER_USER@$SERVER_IP 'jack_metro -b 120'"
echo ""
