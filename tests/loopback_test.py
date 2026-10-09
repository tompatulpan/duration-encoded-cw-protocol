#!/usr/bin/env python3
"""
Automated loopback test harness for the v2 modular protocol variants.

Tests, without any network or audio hardware:
  1. Unit tests of the shared wire format in protocol/base.py
     (timing encode/decode, packet round-trip, EOT flag).
  2. End-to-end loopback tests of each sender/receiver pair in apps/:
     - UDP duration-based   (port default: 47355)
     - UDP timestamp-based (port default: 47357)
     - TCP timestamp-based (port default: 47356)

Each pair test spawns the receiver as a subprocess (audio disabled), runs
the sender against 127.0.0.1, then interrupts the receiver and validates
its printed output: event counts, EOT, loss rate and received dit timing.

Usage:
    python3 tests/loopback_test.py [--message "CQ TEST"] [--wpm 25] [--verbose]

Exit code 0 if all tests pass, 1 otherwise.
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MORSE_CODE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',   'E': '.',
    'F': '..-.',  'G': '--.',   'H': '....',  'I': '..',    'J': '.---',
    'K': '-.-',   'L': '.-..',  'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',  'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',  'Y': '-.--',
    'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '/': '-..-.',  '?': '..--..', '.': '.-.-.-', ',': '--..--',
}

PASS = []
FAIL = []


def report(name, ok, detail=""):
    if ok:
        PASS.append(name)
        print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}" + (f"  ({detail})" if detail else ""))


# ---------------------------------------------------------------
# Unit tests: protocol/base.py wire format
# ---------------------------------------------------------------

def unit_tests():
    print("\n=== Unit tests: protocol/base.py ===")
    sys.path.insert(0, REPO)
    from protocol.base import CWProtocolBase, PROTOCOL_VERSION

    p = CWProtocolBase()

    # 1. Timing encode/decode round-trip with bounded quantization error
    max_err = 0
    for enc in range(128):
        ms = p.decode_timing(enc)
        re_enc = p.encode_timing(ms)
        err = abs(ms - p.decode_timing(re_enc))
        max_err = max(max_err, err)
        assert re_enc <= enc, f"encode(decode({enc})) = {re_enc} > {enc}"
    report("timing round-trip error <= 8ms", max_err <= 8, f"max error {max_err}ms")

    # 2. Monotonic decode
    vals = [p.decode_timing(e) for e in range(128)]
    report("timing decode monotonic", all(a <= b for a, b in zip(vals, vals[1:])))

    # 3. Quantization bands match the spec
    ok = (p.encode_timing(63) == 63 and p.encode_timing(64) == 0x40
          and p.encode_timing(126) == 0x5F and p.encode_timing(384) == 0x7F)
    report("timing band boundaries (63/64/126/384)", ok)

    # 127ms sits in the gap between the 2ms and 8ms bands; it must still
    # round-trip within 2ms (encodes back to the 0x5F band -> 126ms)
    err127 = abs(p.decode_timing(p.encode_timing(127)) - 127)
    report("127ms gap-band value within 2ms", err127 <= 2, f"error {err127}ms")

    # 4. Values above the ceiling are capped, never negative
    report("timing cap at 384ms", p.encode_timing(10000) == 0x7F)

    # 5. Data packet round-trip
    seq_before = p.sequence_number
    pkt = p.create_packet(key_down=True, duration_ms=144)
    parsed = p.parse_packet(pkt)
    ok = (parsed is not None and parsed['version'] == 1
          and parsed['sequence'] == seq_before
          and parsed['client_id'] == 0x42
          and parsed['events'] == [(True, 144)]
          and parsed['eot'] is False)
    report("data packet round-trip", ok)

    # 6. EOT packet round-trip
    pkt = p.create_eot_packet()
    parsed = p.parse_packet(pkt)
    ok = (parsed is not None and len(pkt) == 3 and parsed['eot'] is True
          and parsed['events'] == [])
    report("EOT packet round-trip", ok)

    # 7. Multi-event payload parsing
    pkt = p.create_packet(key_down=False, duration_ms=48) + bytes([0x80 + 63])
    parsed = p.parse_packet(pkt)
    ok = parsed is not None and parsed['events'][1] == (True, 63)
    report("multi-event payload parsing", ok)

    # 8. Truncated packets rejected
    report("truncated packet rejected", p.parse_packet(b'\x40\x00') is None)

    # 9. Sequence number wraps at 256
    p2 = CWProtocolBase()
    p2.sequence_number = 255
    p2.create_packet(True, 10)
    report("sequence wrap at 256", p2.sequence_number == 0)


# ---------------------------------------------------------------
# Loopback pair tests
# ---------------------------------------------------------------

class Receiver:
    """Receiver subprocess with a background stdout collector."""

    def __init__(self, cmd):
        self.proc = subprocess.Popen(
            cmd, cwd=REPO,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env={**os.environ, 'PYTHONUNBUFFERED': '1'})
        self.output = []
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self):
        for line in self.proc.stdout:
            self.output.append(line)

    def text(self):
        return "".join(self.output)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self._thread.join(timeout=5)
        return self.text()


def wait_for(receiver, marker, timeout=15.0):
    """Block until marker appears in receiver output."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if marker in receiver.text():
            return True
        time.sleep(0.1)
    return False


def expected_events(message):
    """Per apps/test_sender_*.py: exactly 2 events (DOWN+UP) per element."""
    downs = sum(len(MORSE_CODE[c.upper()]) for c in message
                if c.upper() in MORSE_CODE)
    return downs, downs  # DOWN count == UP count


def parse_loss(text):
    for line in text.splitlines():
        if line.startswith("Loss rate:"):
            try:
                return float(line.split(":")[1].strip().rstrip('%'))
            except ValueError:
                return None
    return None


def parse_avg_dit(text):
    for line in text.splitlines():
        if line.startswith("Average dit:"):
            try:
                return float(line.split(":")[1].strip().rstrip('ms'))
            except ValueError:
                return None
    return None


def run_pair(name, sender_cmd, receiver_cmd, message, wpm, verbose,
             ready_marker="listening", connect_marker=None,
             check_loss=True):
    print(f"\n=== Loopback: {name} ===")
    downs, ups = expected_events(message)
    exp_dit = 1200 // wpm

    recv = None
    try:
        recv = Receiver(receiver_cmd)
        if not wait_for(recv, ready_marker):
            report(f"{name}: receiver starts", False, "no ready marker")
            return
        if connect_marker and not wait_for(recv, connect_marker):
            report(f"{name}: receiver connects", False, "no connect marker")
            return

        t0 = time.time()
        sender = subprocess.run(sender_cmd, cwd=REPO, capture_output=True,
                                text=True, timeout=120)
        send_s = time.time() - t0

        # Wait for the receiver to drain its jitter buffer and report EOT
        wait_for(recv, "[EOT]", timeout=15)
        time.sleep(1.0)
        output = recv.stop()

        if verbose:
            print(f"--- sender output ---\n{sender.stdout}")
            print(f"--- receiver output ---\n{output}")

        report(f"{name}: sender exits cleanly", sender.returncode == 0,
               f"rc={sender.returncode}")
        report(f"{name}: receiver started", True, f"send time {send_s:.1f}s")

        got_down = output.count("\u25a0")
        got_up = output.count("\u00b7")
        report(f"{name}: DOWN events", got_down == downs,
               f"expected {downs}, got {got_down}")
        report(f"{name}: UP events", got_up == ups,
               f"expected {ups}, got {got_up}")

        report(f"{name}: EOT received", "[EOT]" in output)

        loss = parse_loss(output)
        if check_loss:
            if loss is not None:
                report(f"{name}: loss rate 0%", loss == 0.0, f"{loss}%")
            else:
                report(f"{name}: loss rate reported", False,
                       "no loss line found")
        else:
            report(f"{name}: loss tracking skipped",
                   "Packets received" in output or "Total events" in output,
                   "not tracked for TCP by design")

        avg_dit = parse_avg_dit(output)
        if avg_dit is not None:
            report(f"{name}: avg dit ~{exp_dit}ms",
                   abs(avg_dit - exp_dit) <= max(8, exp_dit * 0.2),
                   f"{avg_dit:.1f}ms")
        else:
            report(f"{name}: timing stats reported", False,
                   "no 'Average dit' line")
    finally:
        if recv is not None:
            recv.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--message', default='CQ TEST')
    parser.add_argument('--wpm', type=int, default=25)
    parser.add_argument('--port-base', type=int, default=47350,
                        help='Base port; variants use +5 (UDP), +6 (TCP-TS), +7 (UDP-TS)')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    py = sys.executable
    pb = args.port_base

    unit_tests()

    run_pair(
        "UDP",
        [py, 'apps/test_sender_udp.py', '127.0.0.1', str(args.wpm),
         args.message, '--port', str(pb + 5), '--no-sidetone'],
        [py, 'apps/test_receiver_udp.py', '--port', str(pb + 5),
         '--no-audio'],
        args.message, args.wpm, args.verbose)

    run_pair(
        "UDP-TS",
        [py, 'apps/test_sender_udp_ts.py', '127.0.0.1', str(args.wpm),
         args.message, '--port', str(pb + 7), '--no-sidetone'],
        [py, 'apps/test_receiver_udp_ts.py', '--port', str(pb + 7),
         '--no-audio', '--jitter-buffer', '150'],
        args.message, args.wpm, args.verbose)

    run_pair(
        "TCP-TS",
        [py, 'apps/test_sender_tcp_ts.py', '127.0.0.1', str(args.wpm),
         args.message, '--port', str(pb + 6), '--no-sidetone'],
        [py, 'apps/test_receiver_tcp_ts.py', '--port', str(pb + 6),
         '--no-audio', '--jitter-buffer', '150'],
        args.message, args.wpm, args.verbose,
        ready_marker="Waiting for connection",
        check_loss=False)

    print("\n" + "=" * 60)
    print(f"RESULTS: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("Failed checks:")
        for f in FAIL:
            print(f"  - {f}")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == '__main__':
    exit(main())
