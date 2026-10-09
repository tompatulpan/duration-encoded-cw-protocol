# Repository Guidelines - Duration-Encoded CW Protocol

## Project Overview

This repository implements the **Duration-Encoded CW (DECW)** protocol for
transmitting Morse code key events with precise timing over UDP/TCP.

See [VERSIONS.md](../VERSIONS.md) for the authoritative project map. Summary:

- **v2 (active development)** - modular packages at the repository root:
  `protocol/`, `buffer/`, `audio/`, `keyer/`, `apps/`
- **v1 (archived)** - `versions/v1-legacy/`, flat single-file scripts.
  Reference only; do not add features there.
- `temp/` - parked unused material (gitignored, safe to delete).

## Core Architecture (v2)

```
protocol/base.py     CWProtocolBase: packet encode/decode, timing codec
protocol/udp.py      CWProtocolUDP: UDP duration-based
protocol/udp_ts.py   CWProtocolUDPTimestamp: UDP + relative timestamps
protocol/tcp_ts.py   CWProtocolTCPTimestamp: TCP length-framing + timestamps
protocol/stats.py    CWTimingStats
buffer/jitter.py     JitterBuffer (relative + timestamp-based scheduling)
audio/sidetone.py    SidetoneGenerator (PyAudio, optional)
audio/gpio.py        GPIOKeyer (RPi.GPIO, optional)
keyer/               Wrapper around ../vail-adapter-lib (IambicKeyer)
apps/                Test senders/receivers for each transport
```

**Key rules:**

- Shared components live in exactly one module (`buffer/jitter.py`,
  `audio/sidetone.py`). Never duplicate them into apps.
- Apps add the repository root to `sys.path` and import via the packages
  (`from protocol.udp import CWProtocolUDP`).
- All optional dependencies (pyaudio, numpy, RPi.GPIO, vail-adapter-lib)
  must degrade gracefully at import time.

## Protocol Semantics (critical)

- A packet describes a state transition plus the **duration of the previous
  state**. Receiver plays the previous state for its duration, then switches.
- v2 packet format: 4-byte header (flags / sequence / client_id) + one event
  byte per key event (bit 7 = key-down, bits 6-0 = encoded duration).
- v2 timing codec caps at 384 ms (1 ms resolution up to 63 ms, 2 ms to 126,
  8 ms to 384). Word/letter spaces are not packetized - senders sleep for
  them and the receiver's buffer resets its timeline on word-space gaps.
- Timestamp variants add a 4-byte relative timestamp (ms since first packet
  of the transmission) for burst-resistant absolute scheduling.
- Ports: UDP duration 7355, TCP+TS 7356, UDP+TS 7357. Note that v1 and v2
  use **different packet formats on the same port 7355** - they are not
  wire-compatible.

## Conventions

- Match the existing style: argparse CLIs, `[TAG]` prefixed console output,
  graceful KeyboardInterrupt shutdown, statistics printed on exit.
- Keep modules stdlib-only where possible; optional heavy deps behind
  try/except at import.
- Timing-sensitive code must not block the audio/playout threads.
