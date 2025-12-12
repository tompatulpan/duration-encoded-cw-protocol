#!/bin/bash
# Local testing script

echo "==================================================="
echo "CW Studio - Local Testing"
echo "==================================================="
echo ""
echo "Starting Cloudflare Worker (dev mode)..."
echo ""

cd worker

# Check if wrangler is available
if ! command -v npx &> /dev/null; then
    echo "Error: npx not found. Please install Node.js"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

echo ""
echo "Worker will be available at: http://localhost:8787"
echo "WebSocket endpoint: ws://localhost:8787"
echo ""
echo "In another terminal, run:"
echo "  cd public && python3 -m http.server 8000"
echo ""
echo "Then open: http://localhost:8000/index.html"
echo ""
echo "Press Ctrl+C to stop"
echo "==================================================="
echo ""

npx wrangler dev
