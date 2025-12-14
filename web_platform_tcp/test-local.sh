#!/bin/bash
# Local testing script - Enhanced with full setup

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}===================================================${NC}"
echo -e "${BLUE}CW Studio - Local Testing (Enhanced)${NC}"
echo -e "${BLUE}===================================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check prerequisites
if ! command -v npx &> /dev/null; then
    echo "Error: npx not found. Please install Node.js"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites OK${NC}"
echo ""

# Kill any existing processes
echo "Cleaning up old processes..."
pkill -9 -f "wrangler dev" 2>/dev/null || true
pkill -9 -f "http.server 8000" 2>/dev/null || true
lsof -ti:8788 | xargs kill -9 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 2
echo ""

# Start worker in background
echo -e "${BLUE}Starting Cloudflare Worker...${NC}"
cd "$SCRIPT_DIR/worker"
npx wrangler dev --port 8788 > /tmp/wrangler.log 2>&1 &
WORKER_PID=$!

# Wait for worker to be ready
echo -n "Waiting for worker"
for i in {1..20}; do
    if grep -q "Ready on" /tmp/wrangler.log 2>/dev/null; then
        echo ""
        echo -e "${GREEN}✓ Worker ready on http://localhost:8788${NC}"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# Start web server in background
echo -e "${BLUE}Starting web server...${NC}"
cd "$SCRIPT_DIR/public"
python3 -m http.server 8000 > /tmp/webserver.log 2>&1 &
WEB_PID=$!
sleep 2
echo -e "${GREEN}✓ Web server ready on http://localhost:8000${NC}"
echo ""

# Display instructions
echo -e "${BLUE}===================================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${BLUE}===================================================${NC}"
echo ""
echo -e "${YELLOW}Services running:${NC}"
echo -e "  • Worker:     http://localhost:8788"
echo -e "  • Web page:   http://localhost:8000"
echo ""
echo -e "${YELLOW}Test Instructions:${NC}"
echo -e "  1. Open browser: ${GREEN}http://localhost:8000/room.html${NC}"
echo -e "  2. In the page, change server URL to: ${GREEN}ws://localhost:8788${NC}"
echo -e "  3. Click ${GREEN}Connect${NC}"
echo -e "  4. In another terminal, run test sender:"
echo -e "     ${GREEN}cd $SCRIPT_DIR${NC}"
echo -e "     ${GREEN}python3 test_usb_key_sender_web.py --server ws://localhost:8788 --callsign TEST --wpm 25${NC}"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo -e "  • Worker:  tail -f /tmp/wrangler.log"
echo -e "  • Web:     tail -f /tmp/webserver.log"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo -e "${BLUE}===================================================${NC}"
echo ""

# Try to open browser
if command -v xdg-open &> /dev/null; then
    echo "Opening browser..."
    xdg-open "http://localhost:8000/room.html" 2>/dev/null &
fi

# Keep running and show logs
trap "echo ''; echo 'Stopping services...'; kill $WORKER_PID $WEB_PID 2>/dev/null; pkill -9 -f 'wrangler dev' 2>/dev/null; pkill -9 -f 'http.server 8000' 2>/dev/null; exit 0" INT TERM

# Show worker logs
tail -f /tmp/wrangler.log
