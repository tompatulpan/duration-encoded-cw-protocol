#!/bin/bash
# Test USB keyer with web platform
#
# Usage:
#   ./test-usb-keyer.sh [mode] [wpm]
#
# Modes:
#   straight   - Straight key (default)
#   iambic-a   - Iambic Mode A
#   iambic-b   - Iambic Mode B
#
# Examples:
#   ./test-usb-keyer.sh straight     # Straight key
#   ./test-usb-keyer.sh iambic-b 25  # Iambic Mode B at 25 WPM

MODE=${1:-straight}
WPM=${2:-20}
SERVER="ws://localhost:8787"
CALLSIGN="SM0ONR"
PORT="/dev/ttyUSB0"

echo "Starting USB keyer..."
echo "  Mode: $MODE"
echo "  WPM: $WPM"
echo "  Server: $SERVER"
echo "  Callsign: $CALLSIGN"
echo "  Port: $PORT"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 cw_usb_key_sender_web.py \
    --server "$SERVER" \
    --callsign "$CALLSIGN" \
    --port "$PORT" \
    --mode "$MODE" \
    --wpm "$WPM" \
    --debug
