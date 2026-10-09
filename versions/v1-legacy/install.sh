#!/bin/bash
# CW Protocol Sender - Linux Installation Script
# Installs Python dependencies and creates launcher commands

set -e  # Exit on any error

echo "======================================"
echo "CW Protocol Sender - Linux Installer"
echo "======================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python 3 installation
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found!${NC}"
    echo "Install Python 3.6+ with:"
    echo "  Fedora:      sudo dnf install python3"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓${NC} Found Python $PYTHON_VERSION"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${YELLOW}⚠ pip3 not found. Installing...${NC}"
    sudo dnf install python3-pip || sudo apt install python3-pip
fi

# Get installation directory (where this script is located)
INSTALL_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo ""
echo "Installation directory: $INSTALL_DIR"
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
echo "------------------------------------"

# Try to install pyserial (required)
echo "Installing pyserial (USB serial support)..."
if pip3 install --user pyserial>=3.5; then
    echo -e "${GREEN}✓${NC} pyserial installed"
else
    echo -e "${RED}❌ Failed to install pyserial${NC}"
    exit 1
fi

# Try to install audio dependencies (optional)
echo ""
echo "Installing audio dependencies (optional)..."
if pip3 install --user pyaudio>=0.2.11 numpy>=1.19.0 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Audio support installed (PyAudio + NumPy)"
else
    echo -e "${YELLOW}⚠ Audio dependencies failed (optional)${NC}"
    echo "  To enable sidetone, install system audio libraries first:"
    echo "    Fedora:      sudo dnf install python3-pyaudio portaudio"
    echo "    Ubuntu/Debian: sudo apt install python3-pyaudio portaudio19-dev"
    echo "  Then run: pip3 install --user pyaudio numpy"
    echo ""
    echo "  Continuing without audio (senders will work, just no sidetone)..."
fi

# Try to install websockets (optional, for web platform sender)
echo ""
echo "Installing WebSocket support (optional)..."
if pip3 install --user websockets>=10.0 2>/dev/null; then
    echo -e "${GREEN}✓${NC} WebSocket support installed"
else
    echo -e "${YELLOW}⚠ WebSocket installation failed (optional)${NC}"
    echo "  Only needed for web platform sender (cw_usb_key_sender_web.py)"
fi

# Check for serial port permissions
echo ""
echo "Checking serial port permissions..."
if groups | grep -q "dialout\|uucp"; then
    echo -e "${GREEN}✓${NC} User has serial port access"
else
    echo -e "${YELLOW}⚠ USB serial port access not configured${NC}"
    echo "  Add your user to dialout group:"
    echo "    sudo usermod -a -G dialout $USER"
    echo "  Then log out and back in for changes to take effect"
fi

# Create launcher scripts
echo ""
echo "Creating launcher commands..."
echo "------------------------------------"

# Create ~/bin directory if it doesn't exist
mkdir -p "$HOME/bin"

# Create launcher for USB key sender (TCP+TS, recommended)
cat > "$HOME/bin/cw-usb-sender" << 'EOF'
#!/bin/bash
# CW USB Key Sender (TCP with Timestamps - WiFi optimized)
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")/../Documents/Projekt/CW/protocol/test_implementation"
cd "$SCRIPT_DIR" 2>/dev/null || cd "$(dirname "$0")"
python3 cw_usb_key_sender_tcp_ts.py "$@"
EOF

# Create launcher for auto sender (text-to-CW)
cat > "$HOME/bin/cw-auto-sender" << 'EOF'
#!/bin/bash
# CW Auto Sender (Text-to-CW, TCP with Timestamps)
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")/../Documents/Projekt/CW/protocol/test_implementation"
cd "$SCRIPT_DIR" 2>/dev/null || cd "$(dirname "$0")"
python3 cw_auto_sender_tcp_ts.py "$@"
EOF

# Create launcher for web platform sender
cat > "$HOME/bin/cw-web-sender" << 'EOF'
#!/bin/bash
# CW Web Platform Sender (WebSocket to Cloudflare Worker)
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")/../Documents/Projekt/CW/protocol/web_platform_tcp"
cd "$SCRIPT_DIR" 2>/dev/null || cd "$(dirname "$0")"
python3 cw_usb_key_sender_web.py "$@"
EOF

# Create launcher for automated web sender
cat > "$HOME/bin/cw-auto-web-sender" << 'EOF'
#!/bin/bash
# CW Automated Web Sender (Text-to-CW via WebSocket)
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")/../Documents/Projekt/CW/protocol/web_platform_tcp"
cd "$SCRIPT_DIR" 2>/dev/null || cd "$(dirname "$0")"
python3 cw_auto_sender_web.py "$@"
EOF

# Make launchers executable
chmod +x "$HOME/bin/cw-usb-sender"
chmod +x "$HOME/bin/cw-auto-sender"
chmod +x "$HOME/bin/cw-web-sender"
chmod +x "$HOME/bin/cw-auto-web-sender"

echo -e "${GREEN}✓${NC} Created launchers in ~/bin/"

# Check if ~/bin is in PATH
if [[ ":$PATH:" == *":$HOME/bin:"* ]]; then
    echo -e "${GREEN}✓${NC} ~/bin is already in PATH"
else
    echo -e "${YELLOW}⚠ ~/bin is not in PATH${NC}"
    echo "  Add this line to ~/.bashrc (or ~/.zshrc):"
    echo "    export PATH=\"\$HOME/bin:\$PATH\""
    echo ""
    echo "  Then run: source ~/.bashrc"
fi

# Copy example config to home directory
if [ ! -f "$HOME/.cw_sender.ini" ]; then
    echo ""
    echo "Creating example config file..."
    cp "$INSTALL_DIR/cw_sender.ini.example" "$HOME/.cw_sender.ini"
    echo -e "${GREEN}✓${NC} Created ~/.cw_sender.ini"
    echo "  Edit this file to set your default host, WPM, callsign, etc."
else
    echo ""
    echo -e "${YELLOW}⚠${NC} ~/.cw_sender.ini already exists (not overwriting)"
fi

# Installation complete
echo ""
echo "======================================"
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo "======================================"
echo ""
echo "Available commands:"
echo "  cw-usb-sender       - USB key sender (physical paddle/key)"
echo "  cw-auto-sender      - Automated text-to-CW sender (TCP)"
echo "  cw-web-sender       - Web platform sender (physical key via WebSocket)"
echo "  cw-auto-web-sender  - Automated text-to-CW sender (WebSocket)"
echo ""
echo "Quick Start:"
echo "  1. Edit config: nano ~/.cw_sender.ini"
echo "     (Set your receiver IP, WPM, callsign)"
echo ""
echo "  2. Run with config:"
echo "     cw-usb-sender"
echo ""
echo "  3. Or override with CLI args:"
echo "     cw-usb-sender 192.168.1.100 --wpm 25 --mode iambic-b"
echo ""
echo "Help:"
echo "  cw-usb-sender --help"
echo ""
echo "Documentation:"
echo "  $INSTALL_DIR/README.md"
echo "  $INSTALL_DIR/DOC/CW_PROTOCOL_SPECIFICATION.md"
echo ""

# Check if PATH update needed
if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo -e "${YELLOW}⚠ IMPORTANT: Add ~/bin to PATH to use commands${NC}"
    echo "  Run: echo 'export PATH=\"\$HOME/bin:\$PATH\"' >> ~/.bashrc"
    echo "  Then: source ~/.bashrc"
    echo ""
fi
