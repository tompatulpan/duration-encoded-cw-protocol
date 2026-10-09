# Repository Restructuring & Migration Plan

**Date:** January 3, 2026  
**Goal:** Modularize the codebase for better reusability and maintainability

---

## Executive Summary

This document outlines the plan to:
1. **Modularize** the core protocol implementation into logical layers
2. **Extract** USB_HID and web_platform_tcp to shared locations
3. **Configure** VS Code workspaces for multi-project development

---

## Current Structure (Problematic)

```
CW/
└── protocol/
    ├── test_implementation/     # Core protocol code
    ├── USB_HID/                 # USB keyer integration (should be shared)
    ├── web_platform_tcp/        # Web platform (should be shared)
    └── protocol.code-workspace  # Single workspace
```

**Problems:**
- USB_HID and web_platform_tcp are trapped inside `protocol/`
- Cannot reuse these components in other CW projects
- Workspace is protocol-centric, not project-centric

---

## Proposed Structure (Modular)

```
CW/
├── protocol/                    # Core protocol implementation
│   ├── protocol/                # Protocol layer (modular)
│   │   ├── __init__.py
│   │   ├── base.py             # CWProtocolBase (abstract)
│   │   ├── udp.py              # CWProtocolUDP
│   │   ├── tcp.py              # CWProtocolTCP
│   │   ├── tcp_ts.py           # CWProtocolTCPTS
│   │   └── stats.py            # CWTimingStats
│   ├── transport/               # Transport layer
│   │   ├── __init__.py
│   │   ├── udp.py              # UDP socket helpers
│   │   └── tcp.py              # TCP socket helpers
│   ├── buffer/                  # Buffering & scheduling
│   │   ├── __init__.py
│   │   ├── jitter.py           # JitterBuffer, JitterBufferTS
│   │   └── strategies.py       # Scheduling strategies
│   ├── audio/                   # Audio layer
│   │   ├── __init__.py
│   │   ├── sidetone.py         # SidetoneGenerator
│   │   └── player.py           # Audio output abstraction
│   ├── keyer/                   # Keyer logic
│   │   ├── __init__.py
│   │   ├── iambic.py           # Iambic keyer
│   │   └── straight.py         # Straight key
│   ├── apps/                    # Application layer
│   │   ├── receiver_udp.py
│   │   ├── receiver_tcp.py
│   │   ├── receiver_tcp_ts.py
│   │   ├── sender_auto.py
│   │   └── sender_usb.py
│   ├── utils/                   # Utilities
│   │   ├── __init__.py
│   │   ├── cli.py              # CLI argument parsing
│   │   └── logging.py          # Logging helpers
│   ├── requirements.txt
│   ├── setup.py                 # Makes protocol pip-installable
│   └── README.md
│
├── USB_HID/                     # Shared USB keyer integration
│   ├── hardware/                # Hardware-specific code
│   │   ├── esp32_cw_keyer.ino
│   │   └── xiao_samd21_hid_key/
│   ├── readers/                 # HID reader implementations
│   │   ├── __init__.py
│   │   └── xiao_hid_reader.py
│   ├── senders/                 # HID-based senders
│   │   ├── cw_xiao_sender_tcp_ts.py
│   │   ├── cw_xiao_sender_udp_ts.py
│   │   └── cw_xiao_sender_web.py
│   ├── scripts/                 # Diagnostic/testing scripts
│   │   ├── diagnose.sh
│   │   └── quick_test.sh
│   ├── DOC/                     # Hardware documentation
│   │   ├── HARDWARE.md
│   │   ├── DEBUGGING_GUIDE.md
│   │   └── SENDERS.md
│   ├── requirements.txt
│   ├── setup.py                 # Makes USB_HID pip-installable
│   └── README.md
│
├── web_platform_tcp/            # Shared web platform
│   ├── worker/                  # Cloudflare Workers backend
│   │   ├── src/
│   │   │   └── index.ts
│   │   ├── wrangler.toml
│   │   └── package.json
│   ├── public/                  # Frontend assets
│   │   ├── index.html
│   │   ├── js/
│   │   │   ├── cw-decoder.js
│   │   │   └── app.js
│   │   └── css/
│   ├── python/                  # Python senders
│   │   ├── cw_auto_sender_web.py
│   │   └── cw_usb_key_sender_web.py
│   ├── DOC/
│   ├── testing/
│   ├── requirements.txt
│   ├── package.json
│   └── README.md
│
├── CW.code-workspace            # Multi-project workspace
└── README.md                    # Top-level project overview
```

---

## Migration Steps

### Phase 1: Create New Directory Structure (Preparation)

1. **Create top-level directories:**
   ```bash
   cd ~/Documents/Projekt/CW
   mkdir -p USB_HID web_platform_tcp
   ```

2. **Create modular subdirectories in protocol:**
   ```bash
   cd protocol
   mkdir -p protocol transport buffer audio keyer apps utils
   touch protocol/__init__.py transport/__init__.py buffer/__init__.py
   touch audio/__init__.py keyer/__init__.py utils/__init__.py
   ```

### Phase 2: Move USB_HID (Critical Path)

```bash
cd ~/Documents/Projekt/CW

# Move USB_HID to shared location
mv protocol/USB_HID/* USB_HID/
rmdir protocol/USB_HID

# Update imports in USB_HID senders to use protocol as package
# (Done in Phase 4)
```

**Files to move:**
- All hardware files (`.ino`, etc.)
- All Python senders (`cw_xiao_sender_*.py`)
- `xiao_hid_reader.py`
- Documentation (`HARDWARE.md`, `DEBUGGING_GUIDE.md`, etc.)
- Scripts (`diagnose.sh`, `quick_test.sh`, etc.)

### Phase 3: Move web_platform_tcp (Critical Path)

```bash
cd ~/Documents/Projekt/CW

# Move web platform to shared location
mv protocol/web_platform_tcp/* web_platform_tcp/
rmdir protocol/web_platform_tcp

# Update imports in web platform senders
# (Done in Phase 4)
```

**Files to move:**
- `worker/` (Cloudflare Workers backend)
- `public/` (Frontend assets)
- `cw_auto_sender_web.py`, `cw_usb_key_sender_web.py`
- Documentation and testing files

### Phase 4: Refactor protocol into Modules

#### 4.1 Create Protocol Layer

```bash
cd ~/Documents/Projekt/CW/protocol

# Extract base protocol
# Move encoding/decoding logic from test_implementation/cw_protocol.py
# to protocol/base.py (abstract base class)

# Create concrete implementations
# protocol/udp.py     ← from cw_protocol.py (UDP-specific)
# protocol/tcp.py     ← from cw_protocol_tcp.py
# protocol/tcp_ts.py  ← from cw_protocol_tcp_ts.py
# protocol/stats.py   ← extract CWTimingStats
```

#### 4.2 Create Buffer Layer

```bash
# Extract buffer logic from test_implementation/cw_receiver.py
# buffer/jitter.py     ← JitterBuffer class
# buffer/strategies.py ← Scheduling strategies (duration vs timestamp)
```

#### 4.3 Create Audio Layer

```bash
# Extract audio from test_implementation/cw_receiver.py
# audio/sidetone.py ← SidetoneGenerator class
# audio/player.py   ← PyAudio abstraction (future)
```

#### 4.4 Create Keyer Layer

```bash
# Extract keyer logic from USB_HID senders
# keyer/iambic.py   ← from cw_usb_key_sender_*.py
# keyer/straight.py ← Straight key logic
```

#### 4.5 Create Apps Layer

```bash
# Move application scripts to apps/
mv test_implementation/cw_receiver_udp_ts.py apps/receiver_udp_ts.py
mv test_implementation/cw_receiver_tcp_ts.py apps/receiver_tcp_ts.py
mv test_implementation/cw_auto_sender_tcp_ts.py apps/sender_auto_tcp_ts.py
# ... etc for all top-level app scripts
```

#### 4.6 Create Utils Layer

```bash
# Create utility modules
# utils/cli.py     ← Common argparse patterns
# utils/logging.py ← Logging helpers
```

### Phase 5: Update Imports

After refactoring, update all imports:

**Before (test_implementation):**
```python
from cw_protocol_tcp_ts import CWProtocolTCPTS
from cw_receiver import JitterBuffer, SidetoneGenerator
```

**After (modular):**
```python
from protocol.tcp_ts import CWProtocolTCPTS
from buffer.jitter import JitterBuffer
from audio.sidetone import SidetoneGenerator
```

**In USB_HID senders:**
```python
# Before (relative import from test_implementation)
import sys
sys.path.append('../test_implementation')
from cw_protocol_tcp_ts import CWProtocolTCPTS

# After (package import)
from protocol.tcp_ts import CWProtocolTCPTS
# or if installed: pip install -e ~/Documents/Projekt/CW/protocol
```

**In web_platform_tcp senders:**
```python
# Same pattern as USB_HID
from protocol.tcp_ts import CWProtocolTCPTS
from keyer.iambic import IambicKeyer
```

### Phase 6: Create setup.py Files (Make Packages Installable)

#### protocol/setup.py

```python
from setuptools import setup, find_packages

setup(
    name='cw-protocol',
    version='1.0.0',
    description='Duration-Encoded CW Protocol Implementation',
    packages=find_packages(),
    install_requires=[
        'numpy',
        'pyaudio',
    ],
    python_requires='>=3.7',
)
```

#### USB_HID/setup.py

```python
from setuptools import setup, find_packages

setup(
    name='cw-usb-hid',
    version='1.0.0',
    description='USB HID Keyer Integration for CW Protocol',
    packages=find_packages(),
    install_requires=[
        'cw-protocol',  # Dependency on protocol package
        'pyserial',
        'evdev',
    ],
    python_requires='>=3.7',
)
```

#### web_platform_tcp/setup.py

```python
from setuptools import setup, find_packages

setup(
    name='cw-web-platform',
    version='1.0.0',
    description='Web Platform for CW Protocol over WebSocket',
    packages=find_packages(where='python'),
    package_dir={'': 'python'},
    install_requires=[
        'cw-protocol',  # Dependency on protocol package
        'websockets',
    ],
    python_requires='>=3.7',
)
```

### Phase 7: Configure VS Code Workspaces

#### Create CW.code-workspace (Multi-Project Workspace)

```json
{
  "folders": [
    {
      "name": "CW Protocol",
      "path": "protocol"
    },
    {
      "name": "USB HID Keyer",
      "path": "USB_HID"
    },
    {
      "name": "Web Platform",
      "path": "web_platform_tcp"
    }
  ],
  "settings": {
    "python.defaultInterpreterPath": "${workspaceFolder:CW Protocol}/.venv/bin/python",
    "python.analysis.extraPaths": [
      "${workspaceFolder:CW Protocol}",
      "${workspaceFolder:USB HID Keyer}",
      "${workspaceFolder:Web Platform}/python"
    ],
    "files.exclude": {
      "**/__pycache__": true,
      "**/*.pyc": true
    }
  },
  "extensions": {
    "recommendations": [
      "ms-python.python",
      "ms-python.vscode-pylance",
      "ms-vscode.cmake-tools"
    ]
  }
}
```

### Phase 8: Install Packages in Development Mode

```bash
# Create virtual environment (optional but recommended)
cd ~/Documents/Projekt/CW
python3 -m venv .venv
source .venv/bin/activate

# Install protocol package (base dependency)
pip install -e protocol/

# Install USB_HID package (depends on protocol)
pip install -e USB_HID/

# Install web platform package (depends on protocol)
pip install -e web_platform_tcp/
```

**Benefits of `-e` (editable) mode:**
- Changes to source code immediately available
- No need to reinstall after edits
- Import from anywhere: `from protocol.tcp_ts import CWProtocolTCPTS`

---

## Testing Strategy

### Phase-by-Phase Validation

**After Phase 2 (USB_HID move):**
```bash
cd ~/Documents/Projekt/CW/USB_HID
python3 cw_xiao_sender_tcp_ts.py localhost 25
# Verify USB keyer still works
```

**After Phase 3 (web_platform_tcp move):**
```bash
cd ~/Documents/Projekt/CW/web_platform_tcp
python3 python/cw_auto_sender_web.py wss://your-worker.workers.dev SM5ABC
# Verify web sender still works
```

**After Phase 4-5 (modular refactor):**
```bash
cd ~/Documents/Projekt/CW/protocol
python3 apps/receiver_tcp_ts.py --jitter-buffer 150
python3 apps/sender_auto_tcp_ts.py localhost 25 "CQ CQ"
# Verify core protocol still works
```

**After Phase 8 (package install):**
```bash
# From any directory
python3 -c "from protocol.tcp_ts import CWProtocolTCPTS; print('✓ Protocol imports work')"
python3 -c "from readers.xiao_hid_reader import XiaoHIDReader; print('✓ USB_HID imports work')"
```

### Regression Testing

Run automated tests after each phase:
```bash
cd ~/Documents/Projekt/CW/protocol
python3 -m pytest testing/
```

---

## Benefits of New Structure

### 1. **Reusability**
- USB_HID can be used in any CW project (not just protocol)
- Web platform can support multiple backends
- Protocol can be imported as a library

### 2. **Maintainability**
- Clear separation of concerns (protocol, transport, buffer, audio)
- Single source of truth for shared components
- Easier to locate and fix bugs

### 3. **Testability**
- Each module can be unit tested in isolation
- Mock interfaces for integration testing
- Smaller, focused test suites

### 4. **Extensibility**
- Add new protocols without touching existing code
- Plug in new keyer types (bug, cootie, etc.)
- Swap audio backends (JACK, PipeWire, etc.)

### 5. **Developer Experience**
- Multi-project workspace in VS Code
- Autocomplete works across projects
- Jump-to-definition across packages

---

## Migration Timeline

| Phase | Estimated Time | Risk Level |
|-------|----------------|------------|
| 1. Directory creation | 15 min | Low |
| 2. Move USB_HID | 30 min | Medium |
| 3. Move web_platform_tcp | 30 min | Medium |
| 4. Refactor protocol | 4-6 hours | High |
| 5. Update imports | 2-3 hours | High |
| 6. Create setup.py | 1 hour | Low |
| 7. Configure workspace | 30 min | Low |
| 8. Install packages | 15 min | Low |
| **Total** | **8-12 hours** | - |

**Recommendation:** Execute phases 1-3 first (low risk), then tackle phases 4-5 incrementally (one module at a time).

---

## Rollback Plan

If migration fails:

1. **USB_HID/web_platform_tcp moves:**
   ```bash
   mv ~/Documents/Projekt/CW/USB_HID ~/Documents/Projekt/CW/protocol/
   mv ~/Documents/Projekt/CW/web_platform_tcp ~/Documents/Projekt/CW/protocol/
   ```

2. **Protocol refactor:**
   - Git worktree/branch approach: `git worktree add ../protocol-refactor main`
   - Work in separate branch, merge when stable
   - Keep `test_implementation/` as fallback until refactor complete

---

## Next Steps

1. **Review this document** and approve migration plan
2. **Create git branch** for migration: `git checkout -b refactor/modular-structure`
3. **Execute Phase 1-3** (low risk, big wins)
4. **Execute Phase 4** incrementally:
   - Start with protocol layer (1-2 hours)
   - Then buffer layer (1 hour)
   - Then audio layer (30 min)
   - Then apps layer (1 hour)
5. **Test continuously** after each phase
6. **Merge to main** when all tests pass

---

## Questions to Resolve

- [ ] Keep `test_implementation/` as legacy fallback during migration?
- [ ] Install packages globally or per-project venvs?
- [ ] Document old→new import mapping for external users?
- [ ] Update old/web_platform/ (non-TCP version) or deprecate?
- [ ] Add CI/CD pipeline to test all packages together?

---

**Document Status:** Draft v1.0  
**Last Updated:** January 3, 2026  
**Author:** GitHub Copilot  
**Approval Required:** Yes
