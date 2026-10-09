# CW Protocol Sender - Installation Guide

**Cross-platform Python installation for physical paddle/key senders**

This installer provides the easiest way to run CW protocol senders on Windows or Linux without compiling executables. The Python source code is already cross-platform!

## Prerequisites

### Required
- **Python 3.6 or later**
  - Linux: Usually pre-installed (`python3 --version`)
  - Windows: Download from [python.org](https://www.python.org/downloads/)
    - ⚠️ **Check "Add Python to PATH" during installation!**

### Optional (for full features)
- **USB-to-Serial adapter** (for physical paddle/key input)
  - FTDI, CH340, or CP210x based adapters
  - Drivers usually auto-install on modern Windows 10/11 and Linux
  
- **Audio libraries** (for sidetone feedback)
  - Linux: `portaudio` (installed by script)
  - Windows: Visual C++ Redistributable ([download](https://aka.ms/vs/17/release/vc_redist.x64.exe))

---

## Installation

### Linux (Fedora, Ubuntu, Debian)

1. **Open terminal** in this directory (`test_implementation/`)

2. **Run installer:**
   ```bash
   ./install.sh
   ```

3. **Follow prompts** - The installer will:
   - ✅ Check Python installation
   - ✅ Install dependencies (pyserial, pyaudio, numpy, websockets)
   - ✅ Create launcher commands in `~/bin/`
   - ✅ Copy example config to `~/.cw_sender.ini`
   - ⚠️ Prompt to add user to `dialout` group (for USB serial access)

4. **Add ~/bin to PATH** (if needed):
   ```bash
   echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

5. **Configure serial port access:**
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and back in for changes to take effect
   ```

### Windows (10/11)

1. **Open Command Prompt** in this directory (`test_implementation\`)
   - Right-click folder → "Open in Terminal" or "Command Prompt here"

2. **Run installer:**
   ```cmd
   install.bat
   ```

3. **Follow prompts** - The installer will:
   - ✅ Check Python installation
   - ✅ Install dependencies (pyserial, pyaudio, numpy, websockets)
   - ✅ Create launcher batch files in `%USERPROFILE%\`
   - ✅ Copy example config to `%USERPROFILE%\.cw_sender.ini`

4. **Optional: Add to PATH** (for easier access)
   - Press Windows key → Search "environment variables"
   - Click "Environment Variables" button
   - Under "User variables", select "Path" → "Edit"
   - Click "New" → Add `%USERPROFILE%`
   - Click OK → Restart Command Prompt

---

## Configuration

### Edit Settings File

**Linux:**
```bash
nano ~/.cw_sender.ini
```

**Windows:**
```cmd
notepad %USERPROFILE%\.cw_sender.ini
```

### Essential Settings to Configure

```ini
[network]
host = 192.168.1.100    # ← Change to your receiver's IP address
port = 7356             # TCP+TS (recommended for WiFi)

[operator]
callsign = SM5ABC       # ← Your callsign (for web platform)

[keyer]
mode = iambic-b         # straight, iambic-a, iambic-b, bug
wpm = 25                # Words per minute (15-30 typical)

[serial]
port =                  # Leave empty for auto-detect
auto_detect = yes       # Automatically find USB serial port

[audio]
enabled = yes           # Enable sidetone (requires PyAudio)
volume = 0.3            # 30% volume (0.0 to 1.0)
```

**💡 Tip**: All settings can be overridden via command-line arguments!

---

## Usage

### After Installation

**Linux** (if ~/bin is in PATH):
```bash
# USB key sender (physical paddle/key)
cw-usb-sender

# Automated text sender (TCP)
cw-auto-sender "CQ CQ CQ DE SM5ABC K"

# Web platform sender (physical key via WebSocket, multi-user)
cw-web-sender

# Automated web sender (text-to-CW via WebSocket, multi-user)
cw-auto-web-sender "CQ CQ CQ DE SM5ABC K"
```

**Windows** (if added to PATH):
```cmd
REM USB key sender (physical paddle/key)
cw-usb-sender.bat

REM Automated text sender (TCP)
cw-auto-sender.bat "CQ CQ CQ DE SM5ABC K"

REM Web platform sender (physical key via WebSocket, multi-user)
cw-web-sender.bat

REM Automated web sender (text-to-CW via WebSocket, multi-user)
cw-auto-web-sender.bat "CQ CQ CQ DE SM5ABC K"
```

**Or use full paths** (always works):

**Linux:**
```bash
~/bin/cw-usb-sender
```

**Windows:**
```cmd
%USERPROFILE%\cw-usb-sender.bat
```

### Command-Line Usage

All senders support configuration via command-line arguments (overrides config file):

```bash
# Basic usage (loads settings from config file)
cw-usb-sender

# Override host and WPM
cw-usb-sender 192.168.1.100 --wpm 30

# Full command with all options
cw-usb-sender 192.168.1.100 \
  --wpm 25 \
  --mode iambic-b \
  --serial-port COM3 \
  --no-audio \
  --debug

# Get help
cw-usb-sender --help
```

### Available Senders

| Command | Description | Protocol | Use Case |
|---------|-------------|----------|----------|
| `cw-usb-sender` | Physical paddle/key input | TCP+TS (port 7356) | **Recommended for real operation** |
| `cw-auto-sender` | Automated text-to-CW | TCP+TS (port 7356) | Testing, beacons, demos |
| `cw-web-sender` | Physical key via WebSocket | WebSocket/JSON | Multi-user web platform |
| `cw-auto-web-sender` | Automated text via WebSocket | WebSocket/JSON | Web platform beacons, testing |

**💡 Primary tools**: 
- **Physical keying**: `cw-usb-sender` (TCP+TS, WiFi-optimized) or `cw-web-sender` (multi-user)
- **Automated sending**: `cw-auto-sender` (TCP) or `cw-auto-web-sender` (web platform)

---

## Troubleshooting

### Linux Issues

**Problem**: `permission denied` when accessing USB serial port

**Solution**: Add user to dialout group
```bash
sudo usermod -a -G dialout $USER
# Log out and back in
```

**Problem**: `ModuleNotFoundError: No module named 'pyaudio'`

**Solution**: Install system audio libraries first
```bash
# Fedora
sudo dnf install python3-pyaudio portaudio

# Ubuntu/Debian
sudo apt install python3-pyaudio portaudio19-dev

# Then reinstall
pip3 install --user pyaudio numpy
```

**Problem**: `cw-usb-sender: command not found`

**Solution**: Add ~/bin to PATH
```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Windows Issues

**Problem**: `'python' is not recognized as an internal or external command`

**Solution**: 
1. Reinstall Python from [python.org](https://www.python.org/downloads/)
2. ⚠️ **Check "Add Python to PATH"** during installation
3. Restart Command Prompt

**Problem**: PyAudio installation fails with `error: Microsoft Visual C++ 14.0 is required`

**Solution**: Install Visual C++ Redistributable
1. Download: [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)
2. Run installer
3. Retry: `python -m pip install pyaudio numpy`

**Alternative**: Disable audio in config
```ini
[audio]
enabled = no
```

**Problem**: Serial port not found (auto-detect fails)

**Solution**: Check Device Manager
1. Press Windows key → Search "Device Manager"
2. Expand "Ports (COM & LPT)"
3. Find USB serial adapter (e.g., "USB Serial Port (COM3)")
4. Specify in config:
   ```ini
   [serial]
   port = COM3
   auto_detect = no
   ```

**Problem**: No audio sidetone (but PyAudio installed)

**Solution**: Check audio device in Windows Sound settings
- Right-click speaker icon → "Sound settings"
- Ensure default output device is working
- Test with: `python -m pyaudio` (should not error)

### General Issues

**Problem**: Cannot connect to receiver

**Solution**: Check network
```bash
# Verify receiver is running
# On receiver machine:
python3 cw_receiver_tcp_ts.py --jitter-buffer 150

# Test connectivity
ping 192.168.1.100    # Replace with receiver IP

# Check firewall
# Linux: sudo ufw allow 7356/tcp
# Windows: Windows Firewall → Allow app → Python
```

**Problem**: High latency / audio skips

**Solution**: Increase jitter buffer in config
```ini
[jitter_buffer]
buffer_ms = 200    # Increase from default 150ms
```

**Problem**: State errors during keying

**Solution**: Suppress warnings in config
```ini
[debug]
suppress_state_errors = yes
```

---

## Testing Installation

### Quick Test (No Hardware)

**Linux:**
```bash
# Terminal 1: Start local receiver
cd ~/Documents/Projekt/CW/protocol/test_implementation
python3 cw_receiver_tcp_ts.py --jitter-buffer 100 --no-audio

# Terminal 2: Send test message
cw-auto-sender localhost 25 "TEST"
```

**Windows:**
```cmd
REM Terminal 1: Start local receiver
cd Documents\Projekt\CW\protocol\test_implementation
python cw_receiver_tcp_ts.py --jitter-buffer 100 --no-audio

REM Terminal 2: Send test message
cw-auto-sender.bat localhost 25 "TEST"
```

**Expected output** (receiver):
```
Connected from localhost
Received: T E S T 
```

### Test with USB Key

1. **Connect USB serial adapter** with paddle/straight key
   - Dit paddle → CTS (pin 8)
   - Dah paddle → DSR (pin 6)
   - Common → GND (pin 5)

2. **Check port detection:**
   ```bash
   python3 -c "import serial.tools.list_ports; print([p.device for p in serial.tools.list_ports.comports()])"
   ```

3. **Run USB key sender:**
   ```bash
   cw-usb-sender localhost --debug

### Test Automated Web Sender

**Without physical key (text-to-CW):**

```bash
# Start receiver in browser
# Open: https://your-web-platform.com

# Send test message via WebSocket
cw-auto-web-sender "TEST DE SM5ABC K"
```

**Expected**: Message appears in web platform decoder in real-time
   ```

4. **Key your paddle** - Should see debug output showing key state changes

---

## Advanced Usage

### Multiple Receivers

Send to multiple receivers simultaneously (not implemented yet, but config supports it):

```ini
[network]
# Future feature: comma-separated hosts
hosts = 192.168.1.100, 192.168.1.101
```

### Custom Protocol Selection

Override protocol from command-line:

```bash
# Force UDP instead of TCP+TS (not yet implemented in config loader)
python3 cw_sender.py 192.168.1.100    # UDP sender
python3 cw_sender_tcp.py 192.168.1.100   # TCP duration-based
python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100  # TCP timestamp-based (recommended)
```

### Web Platform Multi-User

Host your own web platform:

```bash
# Deploy Cloudflare Worker (see web_platform_tcp/README.md)
cd web_platform_tcp
npx wrangler deploy

# Use your worker URL
cw-web-sender wss://your-worker.workers.dev --callsign SM5ABC --room contest
```

---

## Uninstallation

### Linux

```bash
# Remove launchers
rm ~/bin/cw-usb-sender ~/bin/cw-auto-sender ~/bin/cw-web-sender

# Remove config
rm ~/.cw_sender.ini

# Remove Python packages (optional)
pip3 uninstall pyserial pyaudio numpy websockets
```

### Windows

```cmd
REM Remove launchers
del %USERPROFILE%\cw-usb-sender.bat
del %USERPROFILE%\cw-auto-sender.bat
del %USERPROFILE%\cw-web-sender.bat

REM Remove config
del %USERPROFILE%\.cw_sender.ini

REM Remove Python packages (optional)
python -m pip uninstall pyserial pyaudio numpy websockets
```

---

## Next Steps

- **Read protocol documentation**: `DOC/CW_PROTOCOL_SPECIFICATION.md`
- **Understand timing**: `DOC/TIMING_DIAGRAMS.md`
- **TCP vs UDP guide**: `DOC/TCP_UDP_COMPARISON.md`
- **Web platform setup**: `../web_platform_tcp/README.md`

---

## Support

**Issues**: Create GitHub issue at repository  
**Documentation**: See `DOC/` directory  
**License**: See `../LICENSE` file

**73 de CW Protocol Team!** 📻
