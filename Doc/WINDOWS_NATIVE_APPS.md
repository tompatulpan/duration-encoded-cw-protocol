# Building Native Windows Applications from CW Senders

**Status**: Planning Phase  
**Date**: December 17, 2025  
**Author**: Documentation for Windows packaging strategy

## Overview

This document describes the approach for packaging CW protocol senders as native Windows executables (.exe) with persistent settings management. The goal is to make the senders accessible to Windows users without requiring Python installation.

## Why Windows Native Apps?

### Current State
- All senders require Python 3.x installation
- Dependencies must be manually installed (pyserial, pyaudio, websockets)
- Configuration is command-line only (no persistence)
- Technical barrier for non-developer users

### Benefits of Native Apps
- **Single-file distribution**: Users download one .exe, no Python needed
- **Persistent settings**: Remember host, WPM, mode between sessions
- **Professional deployment**: Standard Windows application behavior
- **Simplified setup**: Bundles all dependencies (except hardware drivers)

## Windows-Compatible Senders

### ✅ Fully Compatible (Priority Targets)

| Sender | Protocol | Use Case | Dependencies |
|--------|----------|----------|--------------|
| `cw_usb_key_sender_tcp_ts.py` | TCP+TS (port 7356) | Physical paddle/key input | pyserial, pyaudio (opt) |
| `cw_auto_sender_tcp_ts.py` | TCP+TS (port 7356) | Automated text-to-CW | None (stdlib only) |
| `cw_interactive_sender.py` | UDP (port 7355) | Interactive text entry | threading, queue (stdlib) |
| `cw_usb_key_sender_web.py` | WebSocket/JSON | Web platform multi-user | websockets, pyserial |

**Recommended primary target**: `cw_usb_key_sender_tcp_ts.py` (most full-featured, WiFi-optimized)

### ❌ Not Windows Compatible

| Sender | Issue | Alternative |
|--------|-------|-------------|
| `cw_sender.py` (manual keyer) | Requires POSIX `termios`/`tty` | Use USB key sender with hardware |
| `cw_gpio_output*.py` | Raspberry Pi GPIO specific | Receiver-side only, not needed |

## Settings Management Strategy

### Current Implementation (Command-Line Only)

```bash
# Example: Every session requires full args
python3 cw_usb_key_sender_tcp_ts.py 192.168.1.100 \
    --wpm 25 --mode iambic-b --no-audio
```

**Pain points:**
- Repetitive typing for regular use
- No persistence between sessions
- Difficult to remember exact IP addresses
- Settings not portable across machines

### Proposed Solution: INI Configuration Files

**Format**: Windows-standard `.ini` files using Python's `configparser` module

**Location precedence** (highest to lowest):
1. Command-line arguments (override everything)
2. User home directory: `%USERPROFILE%\.cw_sender.ini` (Windows) or `~/.cw_sender.ini` (Linux)
3. Executable directory: `cw_sender.ini` (portable settings)
4. Built-in defaults (hardcoded in Python)

**Example configuration** (`cw_sender.ini`):

```ini
[network]
# Target receiver hostname or IP
host = 192.168.1.100
# TCP+TS port (7356), TCP duration (7355), UDP (7355), UDP+TS (7357)
port = 7356
# Protocol type: tcp-ts, tcp, udp, udp-ts, websocket
protocol = tcp-ts

[operator]
# Your callsign (used by web platform, optional for TCP/UDP)
callsign = SM5ABC

[keyer]
# Keyer mode: straight, iambic-a, iambic-b, bug
mode = iambic-b
# Words per minute (12-35 range, typical 15-30)
wpm = 25

[serial]
# USB serial port (leave empty for auto-detect)
# Windows: COM3, COM4, etc.
# Linux: /dev/ttyUSB0, /dev/ttyACM0
port = 
# Auto-detect if empty? (yes/no)
auto_detect = yes

[audio]
# Enable sidetone (yes/no)
enabled = yes
# TX sidetone frequency (Hz)
tx_frequency = 600
# RX sidetone frequency (Hz, for receivers)
rx_frequency = 700
# Volume (0.0-1.0)
volume = 0.3

[web_platform]
# WebSocket server URL (for web platform sender only)
server = wss://cw-studio-relay.data4-9de.workers.dev
# Room ID (for multi-user sessions)
room = main
# Echo mode for testing (yes/no)
echo = no

[debug]
# Verbose timing output (yes/no)
verbose = no
# Show packet-level debug (yes/no)
packets = no
```

**Implementation approach:**

```python
import configparser
import os
import argparse

def load_settings():
    """Load settings with precedence: CLI > user config > exe dir > defaults"""
    
    # 1. Define defaults
    defaults = {
        'host': 'localhost',
        'port': 7356,
        'protocol': 'tcp-ts',
        'callsign': '',
        'mode': 'iambic-b',
        'wpm': 25,
        'serial_port': '',
        'serial_auto_detect': True,
        'audio_enabled': True,
        'audio_tx_frequency': 600,
        'audio_volume': 0.3,
        'debug_verbose': False,
    }
    
    # 2. Try to load from config files (user home, then exe dir)
    config = configparser.ConfigParser()
    config_paths = [
        os.path.expanduser('~/.cw_sender.ini'),      # Linux/Mac
        os.path.expanduser('~/.cw_sender.ini'),      # Windows (USERPROFILE)
        'cw_sender.ini',                             # Exe directory
    ]
    
    for path in config_paths:
        if os.path.exists(path):
            config.read(path)
            print(f"Loaded settings from: {path}")
            # Merge config into defaults
            if config.has_section('network'):
                defaults['host'] = config.get('network', 'host', fallback=defaults['host'])
                defaults['port'] = config.getint('network', 'port', fallback=defaults['port'])
            # ... (merge other sections)
            break
    
    # 3. Parse command-line args (override config)
    parser = argparse.ArgumentParser(description='CW Sender')
    parser.add_argument('--host', default=defaults['host'], help='Receiver hostname')
    parser.add_argument('--port', type=int, default=defaults['port'], help='Receiver port')
    parser.add_argument('--wpm', type=int, default=defaults['wpm'], help='Words per minute')
    parser.add_argument('--mode', default=defaults['mode'], 
                       choices=['straight', 'iambic-a', 'iambic-b', 'bug'])
    parser.add_argument('--serial-port', default=defaults['serial_port'])
    parser.add_argument('--no-audio', action='store_true', 
                       help='Disable sidetone (overrides config)')
    parser.add_argument('--debug', action='store_true')
    
    args = parser.parse_args()
    
    # 4. Apply CLI overrides
    if args.no_audio:
        defaults['audio_enabled'] = False
    if args.debug:
        defaults['debug_verbose'] = True
    
    return args  # Contains merged settings
```

**Benefits:**
- ✅ Persistent settings (no re-typing)
- ✅ Portable configs (copy .ini to new machine)
- ✅ CLI override flexibility (power users)
- ✅ Cross-platform (works on Linux/Windows)
- ✅ Standard Windows format (INI files familiar to users)

## Code Architecture Improvements

### 1. Extract Shared Components (Reduce Duplication)

**Problem**: Morse tables and iambic keyer logic duplicated across 5+ files

**Current state:**
```
cw_usb_key_sender_tcp_ts.py     ← IambicKeyer class (lines 130-260)
cw_usb_key_sender_udp_ts.py     ← IambicKeyer class (duplicated)
cw_usb_key_sender_with_decoder.py ← IambicKeyer class (duplicated)
cw_auto_sender_tcp_ts.py        ← MORSE_CODE dict (duplicated)
cw_auto_sender.py               ← MORSE_CODE dict (duplicated)
```

**Proposed structure:**

```
test_implementation/
├── morse_tables.py              ← NEW: Centralized Morse code
│   ├── MORSE_CODE dict (A-Z, 0-9, punctuation)
│   ├── encode_text(text) → dit/dah string
│   └── decode_pattern(pattern) → character
│
├── iambic_keyer.py              ← NEW: Reusable keyer logic
│   ├── IambicKeyer class
│   ├── Mode A/B state machine
│   └── WPM-based timing calculation
│
├── cw_usb_key_sender_tcp_ts.py ← UPDATED: Import from shared
└── cw_auto_sender_tcp_ts.py    ← UPDATED: Import from shared
```

**Benefits:**
- Single source of truth for Morse tables
- Fix keyer bugs once, all senders benefit
- Easier to add prosigns (SK, AR, BT, etc.)
- Smaller executable size (no duplication)

### 2. Protocol Module Dependencies

**Good news**: All protocol modules use **only Python standard library**

```python
# cw_protocol.py (base)
import socket        # Built-in
import struct        # Built-in
import time          # Built-in

# cw_protocol_tcp_ts.py (TCP with timestamps)
import socket        # Built-in
import struct        # Built-in
import threading     # Built-in
```

**No external dependencies for core protocol** = Excellent Windows portability!

### 3. Optional Dependencies (Graceful Degradation)

**Audio (PyAudio + NumPy):**
```python
try:
    from cw_receiver import SidetoneGenerator
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Audio unavailable (PyAudio not installed)")
```

**Serial (pyserial):**
```python
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("USB key not available (pyserial not installed)")
```

**Windows alternative for audio:**
```python
# Fallback to Windows built-in beep (simple, no dependencies)
import winsound

def simple_sidetone(key_down):
    if key_down:
        winsound.Beep(600, 1000)  # 600Hz, long duration
```

## PyInstaller Packaging

### What is PyInstaller?

**PyInstaller** bundles Python applications into standalone executables:
- Includes Python interpreter
- Bundles all imported modules
- Packages dependencies (pyserial, pyaudio, etc.)
- Single-file or directory distribution
- Cross-platform (build on Windows for Windows)

### Installation

```bash
pip install pyinstaller
```

### Basic Build Command

```bash
# Single-file executable (easier distribution)
pyinstaller --onefile cw_usb_key_sender_tcp_ts.py

# Result: dist/cw_usb_key_sender_tcp_ts.exe (Windows)
#         dist/cw_usb_key_sender_tcp_ts (Linux)
```

### Advanced .spec File (Better Control)

**Create**: `cw_sender_tcp_ts.spec`

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['cw_usb_key_sender_tcp_ts.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include default config file
        ('cw_sender.ini', '.'),
    ],
    hiddenimports=[
        # Explicitly include protocol modules
        'cw_protocol',
        'cw_protocol_tcp_ts',
        'cw_receiver',  # For SidetoneGenerator
        # Optional dependencies (graceful degradation if missing)
        'pyaudio',
        'numpy',
        'serial',
        'serial.tools.list_ports',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Reduce size: exclude unused modules
        'matplotlib',
        'scipy',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CW_Sender_TCP_TS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,              # Compress executable (smaller size)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # Keep console window (for debug output)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='cw_icon.ico',    # Optional: Add custom icon
)
```

**Build with spec:**
```bash
pyinstaller cw_sender_tcp_ts.spec
```

### Multiple Sender Variants

**Build script**: `build_windows.py`

```python
#!/usr/bin/env python3
"""
Build all CW sender variants for Windows distribution.
Run on Windows or use Wine/cross-compilation.
"""

import os
import subprocess
import sys

SENDERS = [
    {
        'name': 'CW_USB_Key_Sender_TCP_TS',
        'script': 'cw_usb_key_sender_tcp_ts.py',
        'description': 'USB key sender (TCP+TS, WiFi-optimized)',
        'icon': 'icons/keyer.ico',
    },
    {
        'name': 'CW_Auto_Sender_TCP_TS',
        'script': 'cw_auto_sender_tcp_ts.py',
        'description': 'Automated text-to-CW sender (TCP+TS)',
        'icon': 'icons/auto.ico',
    },
    {
        'name': 'CW_Interactive_Sender',
        'script': 'cw_interactive_sender.py',
        'description': 'Interactive text entry sender (UDP)',
        'icon': 'icons/interactive.ico',
    },
    {
        'name': 'CW_Web_Platform_Sender',
        'script': '../web_platform_tcp/cw_usb_key_sender_web.py',
        'description': 'WebSocket sender for web platform',
        'icon': 'icons/web.ico',
    },
]

def build_sender(sender):
    """Build a single sender executable."""
    print(f"\n{'='*60}")
    print(f"Building: {sender['name']}")
    print(f"Description: {sender['description']}")
    print(f"{'='*60}\n")
    
    # PyInstaller command
    cmd = [
        'pyinstaller',
        '--onefile',                    # Single executable
        '--clean',                      # Clean build
        '--name', sender['name'],       # Executable name
        '--console',                    # Keep console window
    ]
    
    # Add icon if exists
    if os.path.exists(sender['icon']):
        cmd.extend(['--icon', sender['icon']])
    
    # Add script
    cmd.append(sender['script'])
    
    # Run build
    result = subprocess.run(cmd, cwd='test_implementation')
    
    if result.returncode != 0:
        print(f"❌ Build failed: {sender['name']}")
        return False
    else:
        print(f"✅ Build successful: {sender['name']}")
        return True

def main():
    print("CW Protocol - Windows Build Script")
    print("=" * 60)
    
    # Check PyInstaller installed
    try:
        subprocess.run(['pyinstaller', '--version'], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ PyInstaller not found. Install with: pip install pyinstaller")
        sys.exit(1)
    
    # Build each sender
    success_count = 0
    for sender in SENDERS:
        if build_sender(sender):
            success_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Build Summary: {success_count}/{len(SENDERS)} successful")
    print("=" * 60)
    
    if success_count == len(SENDERS):
        print("✅ All builds successful!")
        print(f"\nExecutables in: test_implementation/dist/")
    else:
        print("⚠️  Some builds failed. Check output above.")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

**Usage:**
```bash
# From project root
python3 build_windows.py

# Results in: test_implementation/dist/*.exe
```

## Dependencies and Requirements

### Python Version
- **Minimum**: Python 3.6 (asyncio for web platform)
- **Recommended**: Python 3.9+ (better type hints, performance)
- **Tested**: Python 3.11

### Core Dependencies (Always Included)

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| Python stdlib | 3.6+ | Core protocol, networking | PSF |

### Optional Dependencies

| Package | Version | Purpose | Required For | License |
|---------|---------|---------|--------------|---------|
| pyserial | 3.5+ | USB serial port access | USB key senders | BSD |
| pyaudio | 0.2.11+ | Audio sidetone | All senders (optional) | MIT |
| numpy | 1.20+ | Audio waveform generation | PyAudio dependency | BSD |
| websockets | 10.0+ | WebSocket client | Web platform sender | BSD |

### Windows-Specific Requirements

**Visual C++ Redistributable** (for PyAudio):
- Required if users want audio sidetone
- Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
- Alternative: Fallback to `winsound` (no VC++ needed)

**USB Serial Drivers**:
- **FTDI**: https://ftdichip.com/drivers/vcp-drivers/
- **CH340**: http://www.wch-ic.com/downloads/CH341SER_EXE.html
- **CP210x**: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers
- **Note**: Most modern USB-serial adapters auto-install on Windows 10/11

### Build Environment

**On Windows:**
```bash
# Install Python 3.11
# Download from: https://www.python.org/downloads/

# Install dependencies
pip install pyinstaller pyserial pyaudio numpy websockets

# Build
python build_windows.py
```

**Cross-compilation from Linux** (advanced):
```bash
# Install Wine
sudo dnf install wine  # Fedora
sudo apt install wine  # Ubuntu

# Install Windows Python under Wine
wine python-3.11-amd64.exe

# Build with Wine PyInstaller (complex, not recommended)
```

## Testing Checklist

### Pre-Build Testing (Linux/Python)

1. **Test config file loading:**
   ```bash
   # Create test config
   cat > ~/.cw_sender.ini << EOF
   [network]
   host = localhost
   port = 7356
   EOF
   
   # Run sender (should load config)
   python3 cw_auto_sender_tcp_ts.py
   
   # Override with CLI (should override config)
   python3 cw_auto_sender_tcp_ts.py 192.168.1.50 --port 7355
   ```

2. **Test without optional dependencies:**
   ```bash
   # Uninstall PyAudio temporarily
   pip uninstall pyaudio
   
   # Should run without audio (graceful degradation)
   python3 cw_usb_key_sender_tcp_ts.py localhost --no-audio
   ```

3. **Test USB serial detection:**
   ```bash
   # List available ports
   python3 -c "import serial.tools.list_ports; print([p.device for p in serial.tools.list_ports.comports()])"
   
   # Test auto-detect
   python3 cw_usb_key_sender_tcp_ts.py localhost
   ```

### Post-Build Testing (Windows .exe)

1. **Launch from command prompt:**
   ```cmd
   cd dist
   CW_USB_Key_Sender_TCP_TS.exe --help
   ```

2. **Test config file (user home):**
   ```cmd
   notepad %USERPROFILE%\.cw_sender.ini
   REM (Create config, then run .exe)
   CW_USB_Key_Sender_TCP_TS.exe
   ```

3. **Test config file (exe directory):**
   ```cmd
   cd dist
   notepad cw_sender.ini
   REM (Create config in same folder as .exe)
   CW_USB_Key_Sender_TCP_TS.exe
   ```

4. **Test serial port (COM ports):**
   ```cmd
   REM Auto-detect
   CW_USB_Key_Sender_TCP_TS.exe localhost
   
   REM Explicit port
   CW_USB_Key_Sender_TCP_TS.exe localhost --serial-port COM3
   ```

5. **Test audio sidetone:**
   ```cmd
   REM With audio
   CW_USB_Key_Sender_TCP_TS.exe localhost
   
   REM Without audio
   CW_USB_Key_Sender_TCP_TS.exe localhost --no-audio
   ```

6. **Test network connectivity:**
   ```cmd
   REM Start receiver on another machine (192.168.1.100)
   python3 cw_receiver_tcp_ts.py --jitter-buffer 150
   
   REM Connect from Windows
   CW_USB_Key_Sender_TCP_TS.exe 192.168.1.100 --wpm 25
   ```

### Regression Testing

**Test matrix** (all combinations should work):

| Sender | Protocol | Config | Audio | Serial | Platform |
|--------|----------|--------|-------|--------|----------|
| USB Key | TCP+TS | INI | PyAudio | COM3 | Windows 10 |
| USB Key | TCP+TS | INI | winsound | COM3 | Windows 11 |
| USB Key | TCP+TS | CLI args | None | Auto | Windows 10 |
| Auto | TCP+TS | INI | PyAudio | N/A | Windows 10 |
| Interactive | UDP | CLI args | None | N/A | Windows 11 |
| Web | WebSocket | INI | PyAudio | COM4 | Windows 10 |

## Troubleshooting

### Build Issues

**Problem**: PyInstaller fails with "Cannot find module"

```
Solution 1: Add to hiddenimports in .spec file
hiddenimports=['missing_module']

Solution 2: Install missing dependency
pip install missing_module
```

**Problem**: Executable size too large (>50 MB)

```
Solution 1: Use --exclude to remove unused modules
--exclude-module matplotlib --exclude-module scipy

Solution 2: Enable UPX compression
upx=True in .spec file
```

**Problem**: "msvcp140.dll missing" error on Windows

```
Solution: User needs Visual C++ Redistributable
Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
```

### Runtime Issues

**Problem**: Config file not found

```
Check precedence:
1. %USERPROFILE%\.cw_sender.ini
2. C:\path\to\exe\cw_sender.ini
3. Built-in defaults

Debug: Add print statement to show loaded path
```

**Problem**: Serial port not detected

```
Check: Device Manager → Ports (COM & LPT)
- Is USB adapter listed?
- What COM number? (COM3, COM4, etc.)

Test manually:
CW_USB_Key_Sender_TCP_TS.exe localhost --serial-port COM3
```

**Problem**: No audio sidetone

```
Check 1: Is PyAudio bundled?
- Look for _portaudio.pyd in exe

Check 2: Is audio enabled in config?
[audio]
enabled = yes

Check 3: Try winsound fallback
- Rebuild with winsound instead of PyAudio
```

**Problem**: "Connection refused" error

```
Check 1: Is receiver running?
python3 cw_receiver_tcp_ts.py --jitter-buffer 150

Check 2: Correct IP address?
ping 192.168.1.100

Check 3: Firewall blocking port 7356?
Windows Firewall → Allow app
```

## Distribution Strategy

### File Naming Convention

```
CW_Sender_<Type>_<Protocol>_<Version>.exe

Examples:
CW_Sender_USB_Key_TCP_TS_v1.0.exe
CW_Sender_Auto_TCP_TS_v1.0.exe
CW_Sender_Interactive_UDP_v1.0.exe
CW_Sender_Web_Platform_v1.0.exe
```

### Package Contents

**Minimal distribution** (single .exe):
```
CW_Sender_USB_Key_TCP_TS_v1.0.exe    ← Standalone executable
README.txt                            ← Quick start guide
LICENSE.txt                           ← MIT/BSD license
```

**Full distribution** (with examples):
```
CW_Sender_USB_Key_TCP_TS_v1.0.exe
README.txt
LICENSE.txt
examples/
    ├── cw_sender.ini.example         ← Sample config
    ├── quick_start.bat               ← Batch file for localhost testing
    └── connect_to_receiver.bat       ← Example with remote host
drivers/
    ├── FTDI_VCP_Driver.url           ← Link to FTDI drivers
    ├── CH340_Driver.url              ← Link to CH340 drivers
    └── VC_Redist_x64.url             ← Link to VC++ redistributable
```

### Installation Instructions (for users)

**Quick Start**:
```
1. Download: CW_Sender_USB_Key_TCP_TS_v1.0.exe
2. Run from Command Prompt:
   > CW_Sender_USB_Key_TCP_TS.exe 192.168.1.100 --wpm 25
3. Connect USB key adapter (if not already connected)
4. Start keying!
```

**Advanced Setup** (persistent settings):
```
1. Create config file:
   notepad %USERPROFILE%\.cw_sender.ini

2. Add settings:
   [network]
   host = 192.168.1.100
   port = 7356
   
   [keyer]
   mode = iambic-b
   wpm = 25

3. Run without args:
   > CW_Sender_USB_Key_TCP_TS.exe
   (Loads settings from .ini automatically)
```

## Future Enhancements

### Phase 2: GUI Wrapper (Optional)

**Approach**: Tkinter GUI wrapping command-line sender

**Features**:
- Settings dialog (host, WPM, mode)
- Status display (connected, packets sent, queue depth)
- Start/Stop buttons
- System tray icon (minimize to tray)

**Benefits**:
- More user-friendly for non-technical users
- Visual feedback (connection status, errors)
- No command prompt required

**Drawback**:
- Larger executable size
- More complex development/testing

### Phase 3: Windows Service (Advanced)

**Approach**: Run sender as background Windows service

**Use cases**:
- Permanent station setup
- Automatic startup with Windows
- Remote control via network

**Complexity**: High (requires service management, elevated privileges)

### Phase 4: Installer Package

**Approach**: NSIS or WiX installer

**Features**:
- Start Menu shortcuts
- Desktop icon
- File associations (.cwk for keyer profiles?)
- Uninstaller
- Automatic driver installation

**Tools**:
- NSIS (Nullsoft Scriptable Install System) - simpler
- WiX Toolset - more professional, complex

## ✅ Implementation Status: Option 1 (Pure Python) - COMPLETED

**Decision**: Implemented **Option 1 - Pure Python Source Distribution** with cross-platform installers.

### What's Been Implemented

All files created in `test_implementation/` directory:

1. ✅ **`requirements.txt`** - Python dependencies with version constraints
2. ✅ **`cw_sender.ini.example`** - Complete configuration template
3. ✅ **`install.sh`** - Linux installer (auto-installs dependencies, creates launchers)
4. ✅ **`install.bat`** - Windows installer (auto-installs dependencies, creates batch files)
5. ✅ **`INSTALL.md`** - Complete installation and troubleshooting guide

### Installation (Quick Start)

**Linux:**
```bash
cd test_implementation/
./install.sh
```

**Windows:**
```cmd
cd test_implementation\
install.bat
```

Both installers handle:
- ✅ Python version checking
- ✅ Dependency installation (pyserial, pyaudio, numpy, websockets)
- ✅ Launcher creation (`cw-usb-sender`, `cw-auto-sender`, `cw-web-sender`)
- ✅ Config file setup (`~/.cw_sender.ini`)
- ✅ Platform-specific fixes (serial port permissions on Linux, PATH setup)

### Usage After Installation

**Identical on both platforms:**
```bash
# USB key sender (physical paddle)
cw-usb-sender 192.168.1.100 --wpm 25 --mode iambic-b

# With config file (no arguments needed)
cw-usb-sender   # Loads ~/.cw_sender.ini

# Automated text sender
cw-auto-sender localhost 25 "CQ CQ CQ DE SM5ABC K"

# Web platform sender
cw-web-sender wss://cw-studio-relay.data4-9de.workers.dev --callsign SM5ABC
```

### Why Option 1 Was Chosen

**Advantages realized:**
- ✅ **Cross-platform without changes**: Same Python code works on Windows/Linux/Mac
- ✅ **Small download size**: ~50 KB (vs 25 MB for PyInstaller binaries)
- ✅ **Easy updates**: `git pull` or download new .py files
- ✅ **Flexible configuration**: INI files + CLI overrides
- ✅ **Technical audience**: Ham radio operators familiar with Python
- ✅ **Development-friendly**: Users can modify code if needed

**Trade-offs accepted:**
- ⚠️ Requires Python installation (acceptable for technical users)
- ⚠️ pip dependency management (handled by installers)
- ⚠️ Less "polished" than .exe (but professional enough for ham radio community)

### Configuration System

**Config file precedence** (highest to lowest):
1. Command-line arguments (override everything)
2. User home: `~/.cw_sender.ini` (Linux) or `%USERPROFILE%\.cw_sender.ini` (Windows)
3. Executable directory: `cw_sender.ini` (portable configs)
4. Built-in defaults

**Example config** (`~/.cw_sender.ini`):
```ini
[network]
host = 192.168.1.100
port = 7356          # TCP+TS (WiFi-optimized)

[keyer]
mode = iambic-b
wpm = 25

[serial]
port =               # Empty = auto-detect
auto_detect = yes

[audio]
enabled = yes
volume = 0.3
```

### Future Phases (Optional)

**Phase 2A: Extract Shared Components** (Nice to have)
- Create `morse_tables.py` (centralized Morse code dictionary)
- Create `iambic_keyer.py` (reusable keyer class)
- Update senders to import instead of duplicate code

**Phase 2B: PyInstaller Binaries** (For non-technical users)
- Build Windows .exe and Linux binaries for end-users
- Ship both Python source AND binaries
- Let users choose installation method

**Phase 3: GUI Wrapper** (Optional)
- Tkinter settings dialog
- Status display (connected, packets sent)
- System tray icon

### Recommendations

**For technical users (ham radio operators):**
- ✅ Use Option 1 (Pure Python) - **IMPLEMENTED**
- Fast setup with `install.sh` / `install.bat`
- Full control and easy debugging

**For non-technical users (future):**
- Consider Phase 2B (PyInstaller binaries)
- One-click installation, no Python required
- Larger download, but simpler for end-users

**For now**: Option 1 is **fully functional and ready to use!**

### Recommended Sender

**Primary tool**: `cw-usb-sender` (wraps `cw_usb_key_sender_tcp_ts.py`)

**Rationale**:
- Most full-featured (physical paddle/key support)
- Best protocol (TCP+TS, WiFi-optimized, burst-resistant)
- Real-world use case (ham radio operators)
- Includes optional sidetone
- Well-tested codebase

**Secondary tools**:
- `cw-auto-sender` - Automated text-to-CW (testing, beacons)
- `cw-web-sender` - WebSocket for multi-user web platform

## References

### Related Documentation
- `Doc/TCP_TS_PROTOCOL_SPECIFICATION.md` - Protocol details
- `test_implementation/DOC/CW_PROTOCOL_SPECIFICATION.md` - Packet format
- `test_implementation/README.md` - Current usage examples

### External Resources
- PyInstaller docs: https://pyinstaller.org/en/stable/
- Python configparser: https://docs.python.org/3/library/configparser.html
- pyserial documentation: https://pyserial.readthedocs.io/

### License Compatibility

**CW Protocol**: (Check LICENSE file at project root)
**Dependencies**:
- pyserial: BSD License ✅
- PyAudio: MIT License ✅
- NumPy: BSD License ✅
- websockets: BSD License ✅

All dependencies are permissive licenses, compatible with redistribution in Windows executables.

---

## Next Steps

1. **Decision point**: Which sender to implement first? (Recommend USB key TCP+TS)
2. **Planning**: Detailed implementation timeline for Phase 1A (settings)
3. **Testing environment**: Set up Windows VM or physical Windows machine
4. **Validation**: Test config file approach on Linux first (cross-platform verification)

**Questions to resolve**:
- Should GUI be part of Phase 1 or deferred to Phase 2?
- Do we need multiple protocol variants packaged, or just TCP+TS?
- Config file format: INI vs JSON vs TOML? (Recommend INI for Windows familiarity)
- Icon design needed for .exe branding?
