#!/bin/bash
# Test TCP receiver state reset between transmissions

echo "Starting TCP receiver with jitter buffer..."
python3 cw_receiver_tcp.py --jitter-buffer 100 --no-audio &
RECEIVER_PID=$!

sleep 2

echo ""
echo "=== First transmission: TEST ==="
python3 cw_auto_sender_tcp.py localhost 25 "TEST"

echo ""
echo "Waiting 2 seconds before next transmission..."
sleep 2

echo ""
echo "=== Second transmission: ABC ==="
python3 cw_auto_sender_tcp.py localhost 25 "ABC"

echo ""
echo "Waiting 2 seconds before third transmission..."
sleep 2

echo ""
echo "=== Third transmission: XYZ ==="
python3 cw_auto_sender_tcp.py localhost 25 "XYZ"

echo ""
echo "=== Test complete ==="
sleep 2

kill $RECEIVER_PID 2>/dev/null
wait $RECEIVER_PID 2>/dev/null

echo "Receiver stopped"
