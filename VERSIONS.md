# Project Versions

This project has gone through two major implementation generations. This file
is the authoritative map of what lives where and what is still used.

## Version overview

| Version | Location | Status | Description |
|---------|----------|--------|-------------|
| **v1 - Legacy monolithic** | `versions/v1-legacy/` | Archived, reference only | Flat single-file scripts, one file per sender/receiver variant |
| **v2 - Modular refactor** | `protocol/`, `buffer/`, `audio/`, `keyer/`, `apps/` | Active development (branch `refactor/modular-structure`) | Layered package structure, shared components |

## v1 - Legacy monolithic (`versions/v1-legacy/`)

The original implementation (as it exists on the `main` branch). Every protocol
variant is a standalone script that duplicates its own copy of the keyer,
jitter buffer and sidetone logic.

- UDP packet format: 3 bytes `[sequence][key state][duration]`
- TCP packet format: length-prefix framing
- Includes FEC experiment (`FEC/`) and extensive docs (`DOC/`)
- Nothing in v2 imports from v1; it is kept as reference only

**Do not develop here.** Bug fixes belong in v2 modules.

## v2 - Modular refactor (repository root)

Layered structure extracted from v1 (branch `refactor/modular-structure`,
started January 2026):

```
protocol/   base.py (packet encode/decode, 4-byte header + event bytes)
            udp.py, udp_ts.py, tcp_ts.py, stats.py
buffer/     jitter.py (JitterBuffer - relative and timestamp-based scheduling)
audio/      sidetone.py (SidetoneGenerator), gpio.py (GPIOKeyer)
keyer/      wrapper around ../vail-adapter-lib (IambicKeyer, IambicKeyerSync)
apps/       test senders/receivers for UDP, UDP+TS and TCP+TS
```

Important notes:

- v2 uses a **new packet format** (4-byte header: flags/sequence/client_id,
  then 1 event byte per key event). It is wire-incompatible with v1 even
  though UDP duration-based traffic uses the same port 7355.
- The duration-based TCP module (`protocol/tcp.py`) was never extracted;
  only `tcp_ts.py` exists. Use v1's `cw_protocol_tcp.py` if you need
  duration-based TCP, or port it.
- Word/letter spaces slower than ~384 ms cannot be encoded by the v2 timing
  scheme (capped at 384 ms); practical WPM range is ~10-60.

## Related projects (outside this repository)

- `../USB_HID/` - XIAO SAMD21 / ESP32 hardware keyer firmware and senders
- `../web_platform_tcp/` - browser-based web platform (Cloudflare Workers)
- `../vail-adapter-lib/` - shared keyer library used by `keyer/`

## Parked material (`temp/`, gitignored)

Unused material moved out of the way during the October 2026 cleanup.
Nothing in the active code references it. All of it is safe to delete once
you are sure you do not want it:

| Path | Size | What it is |
|------|------|------------|
| `temp/v1-legacy-venv/` | ~66 MB | Python virtualenv that lived inside v1 (regenerable with pip) |
| `temp/web_platform_legacy/` | ~299 MB | Old web platform copy, mostly `node_modules` (regenerable with npm) |
| `temp/web_platform_tcp_legacy/` | ~1 MB | Older copy of the web platform TCP experiments |
| `temp/usb_hid_legacy/` | ~350 KB | Superseded USB_HID copy (active version is `../USB_HID/`) |
| `temp/experimental_fec_RX/` | 4 KB | Empty leftover directory from removed FEC experiments |
| `temp/v1-legacy-log.txt` | 36 KB | Debug log found in v1 |
