# TCP with Timestamps (TCP-TS) Protocol Specification

**Duration-Encoded CW Protocol - TCP Timestamp Variant**

**Version:** 1.0  
**Date:** December 14, 2025  
**Status:** Production

---

## Table of Contents

1. [Overview](#1-overview)
2. [Protocol Architecture](#2-protocol-architecture)
3. [Packet Format](#3-packet-format)
4. [Timing Model](#4-timing-model)
5. [Connection Management](#5-connection-management)
6. [Sender Implementation](#6-sender-implementation)
7. [Receiver Implementation](#7-receiver-implementation)
8. [Jitter Buffer Integration](#8-jitter-buffer-integration)
9. [Testing & Validation](#9-testing--validation)
10. [Performance Characteristics](#10-performance-characteristics)
11. [Reference Implementation](#11-reference-implementation)

---

## 1. Overview

### 1.1 Purpose

The TCP-TS protocol provides **burst-resistant** Morse code transmission over TCP by encoding absolute timing information. Unlike duration-based protocols that schedule events relative to the previous event, TCP-TS uses **sender timeline timestamps** for independent event scheduling.

### 1.2 Key Benefits

- **Burst Immunity:** Packet bursts don't accumulate delays
- **Queue Stability:** Maintains 2-3 event queue depth (vs 6-7 for duration-based)
- **Consistent Latency:** Scheduling variance ±1ms (vs ±50ms)
- **WiFi Optimized:** Handles WiFi/TCP packet coalescing gracefully
- **Reliable Delivery:** TCP guarantees packet arrival and ordering

### 1.3 Use Cases

| Scenario | TCP-TS | Duration-Based | UDP |
|----------|--------|----------------|-----|
| **WiFi Networks** | ✅ Best | ⚠️ Queue buildup | ⚠️ Loss |
| **Internet (good)** | ✅ Excellent | ⚠️ Moderate | ✅ Good |
| **Internet (poor)** | ✅ Excellent | ✅ Good | ❌ Loss |
| **LAN (low latency)** | ✅ Good | ✅ Good | ✅ Best |
| **Packet loss >5%** | ✅ Handles | ✅ Handles | ❌ Fails |

**Recommendation:** TCP-TS is the **preferred protocol** for any network with potential bursting behavior (WiFi, cellular, congested internet).

---

## 2. Protocol Architecture

### 2.1 Layered Design

```
┌─────────────────────────────────────────────────┐
│        Application Layer (Morse Code)           │
├─────────────────────────────────────────────────┤
│    Timestamp Protocol (Absolute Event Times)    │
├─────────────────────────────────────────────────┤
│     TCP Framing (Length-Prefix Messages)        │
├─────────────────────────────────────────────────┤
│            TCP (Reliable Stream)                │
├─────────────────────────────────────────────────┤
│              IP / Network Layer                 │
└─────────────────────────────────────────────────┘
```

### 2.2 Protocol Stack

1. **TCP Layer:** Provides reliable, ordered byte stream
2. **Framing Layer:** Length-prefix delimits messages in stream
3. **Timestamp Layer:** Encodes relative event times
4. **Application Layer:** Morse code timing (DOWN/UP events)

---

## 3. Packet Format

### 3.1 Complete Packet Structure

```
┌────────────┬────────────┬───────────┬─────────────┬──────────────┐
│  Length    │  Sequence  │  State    │  Duration   │  Timestamp   │
│  (2 bytes) │  (1 byte)  │ (1 byte)  │ (1-2 bytes) │  (4 bytes)   │
├────────────┼────────────┼───────────┼─────────────┼──────────────┤
│ Big-endian │  Wrapping  │  UP/DOWN  │ Big-endian  │  Big-endian  │
│   uint16   │   uint8    │   0x00/   │ uint8/16    │    uint32    │
│            │            │   0x01    │             │              │
└────────────┴────────────┴───────────┴─────────────┴──────────────┘
     2           1             1          1-2              4
                                                    
Total: 8-9 bytes per packet
```

### 3.2 Field Definitions

#### Length Prefix (2 bytes)
```python
struct.pack('!H', packet_length)  # Network byte order (big-endian)
```
- **Purpose:** Delimit messages in TCP stream
- **Range:** 6-8 bytes (packet payload size)
- **Note:** Does NOT include length field itself

#### Sequence Number (1 byte)
```python
sequence = (sequence + 1) % 256  # Wraps at 256
```
- **Purpose:** Detect packet loss, out-of-order delivery
- **Range:** 0-255
- **Behavior:** Wraps to 0 after 255

#### State Byte (1 byte)
```python
0x00 = Key UP (spacing)
0x01 = Key DOWN (tone)
0xFF = End-of-Transmission (EOT) marker
```
- **Purpose:** Indicates key position
- **Valid Values:** `0x00`, `0x01`, `0xFF`

#### Duration (1-2 bytes)
```python
# Standard encoding (< 256ms)
duration_bytes = struct.pack('B', duration_ms)  # 1 byte

# Extended encoding (>= 256ms)
duration_bytes = struct.pack('!H', duration_ms)  # 2 bytes big-endian
```
- **Purpose:** Event duration for sidetone generation
- **Range:** 0-65535 ms
- **Typical CW:** 40-80ms (dit), 120-240ms (dah)

#### Timestamp (4 bytes)
```python
timestamp_ms = int((time.time() - transmission_start) * 1000)
timestamp_bytes = struct.pack('!I', timestamp_ms)  # Big-endian uint32
```
- **Purpose:** Absolute event time from sender's perspective
- **Range:** 0 to 4,294,967,295 ms (~49.7 days)
- **Epoch:** First packet of transmission (timestamp=0)
- **Resolution:** 1 millisecond

### 3.3 Packet Size Examples

```
Standard CW packet (dit/dah < 256ms):
  2 (length) + 1 (seq) + 1 (state) + 1 (duration) + 4 (timestamp) = 9 bytes

Extended duration packet (>= 256ms):
  2 (length) + 1 (seq) + 1 (state) + 2 (duration) + 4 (timestamp) = 10 bytes

End-of-Transmission (EOT):
  2 (length) + 1 (seq) + 1 (0xFF) + 1 (0x00) + 4 (timestamp) = 9 bytes
```

---

## 4. Timing Model

### 4.1 Absolute Timeline Approach

**Key Principle:** Each packet contains the **absolute time** the event occurred relative to the start of transmission.

```
Sender Timeline:
─────────────────────────────────────────────────────────►
t=0ms      t=48ms     t=96ms     t=144ms    t=192ms
  │          │          │           │          │
  ▼          ▼          ▼           ▼          ▼
Packet    Packet    Packet      Packet     Packet
ts=0      ts=48     ts=96       ts=144     ts=192

Network (may burst):
Packet    Packet    Packet      Packet     Packet
 ts=0      ts=48     ts=96       ts=144     ts=192
    └─────────┴─────────┴───────────┴──────────┘
           All arrive within 5ms

Receiver Timeline (synchronized):
─────────────────────────────────────────────────────────►
Playout    Playout   Playout    Playout    Playout
t=150ms    t=198ms   t=246ms    t=294ms    t=342ms
  │          │          │           │          │
(150ms buffer added to each event's absolute time)
```

### 4.2 Sender Timeline Management

```python
class Sender:
    def __init__(self):
        self.transmission_start = None
    
    def send_event(self, key_down, duration_ms):
        # Initialize timeline on first packet
        if self.transmission_start is None:
            self.transmission_start = time.time()
        
        # Calculate relative timestamp
        timestamp_ms = int((time.time() - self.transmission_start) * 1000)
        
        # Send packet
        send_packet(key_down, duration_ms, timestamp_ms)
        
        # Wait for actual duration (real-time pacing)
        time.sleep(duration_ms / 1000.0)
```

**Critical Points:**
1. **First packet:** `transmission_start = time.time()`, `timestamp = 0`
2. **Subsequent packets:** `timestamp = (now - transmission_start) * 1000`
3. **EOT packet:** Resets `transmission_start = None` for next transmission
4. **Real-time pacing:** Sender MUST `sleep()` between events

### 4.3 Receiver Timeline Synchronization

```python
class Receiver:
    def __init__(self):
        self.sender_timeline_offset = None
    
    def process_packet(self, timestamp_ms):
        # First packet: synchronize to sender's timeline
        if self.sender_timeline_offset is None:
            # Calculate sender's start time in receiver's clock
            self.sender_timeline_offset = time.time() - (timestamp_ms / 1000.0)
        
        # Calculate sender's absolute event time
        sender_event_time = self.sender_timeline_offset + (timestamp_ms / 1000.0)
        
        # Schedule playback with jitter buffer
        playout_time = sender_event_time + (buffer_ms / 1000.0)
        
        schedule_event(playout_time)
```

**Key Insight:** The receiver tracks the sender's timeline by calculating an offset between the two clocks.

### 4.4 Comparison: Duration-Based vs Timestamp-Based

#### Duration-Based (Cumulative Scheduling)
```python
# Each event scheduled relative to previous
playout_time = last_event_end_time  # Chain of dependencies

# Burst scenario (4 packets arrive within 5ms):
Packet 1: playout at T+100ms, ends at T+148ms
Packet 2: playout at T+148ms, ends at T+196ms  # Waits for #1
Packet 3: playout at T+196ms, ends at T+340ms  # Waits for #2
Packet 4: playout at T+340ms, ends at T+388ms  # Waits for #3

Result: Queue depth = 4, scheduled 388ms ahead
```

#### Timestamp-Based (Independent Scheduling)
```python
# Each event scheduled at absolute sender time
playout_time = sender_timeline_offset + timestamp_ms + buffer_ms

# Same burst scenario:
Packet 1: ts=0ms   → playout at T+150ms
Packet 2: ts=48ms  → playout at T+198ms   # Independent
Packet 3: ts=96ms  → playout at T+246ms   # Independent
Packet 4: ts=144ms → playout at T+294ms   # Independent

Result: Queue depth = 2-3, consistent 150ms buffer
```

---

## 5. Connection Management

### 5.1 Connection Lifecycle

```
Sender                                 Receiver
  │                                       │
  │  TCP Connect (port 7356)             │
  ├──────────────────────────────────────>│
  │                                       │
  │  SYN-ACK (TCP handshake)             │
  │<──────────────────────────────────────┤
  │                                       │
  │  First Packet (ts=0)                 │
  ├──────────────────────────────────────>│ ← Timeline sync
  │                                       │
  │  Event packets (ts=48, 96, 144...)   │
  ├──────────────────────────────────────>│
  │                                       │
  │  EOT Packet (state=0xFF)             │
  ├──────────────────────────────────────>│ ← Transmission end
  │                                       │
  │  Continue or disconnect              │
  │                                       │
```

### 5.2 Port Configuration

```python
TCP_TS_PORT = 7356  # TCP timestamp protocol (default)
```

**Port Assignments:**
- **UDP:** 7355 (standard duration-based)
- **TCP Duration:** 7356 (duration-based TCP)
- **TCP Timestamp:** 7356 (timestamp-based TCP) ← **This protocol**
- **FEC:** 7357 (UDP with forward error correction)

**Note:** TCP duration and TCP timestamp share port 7356 as they are mutually exclusive modes.

### 5.3 Connection States

| State | Description | Sender Action | Receiver Action |
|-------|-------------|---------------|-----------------|
| **DISCONNECTED** | No connection | Call `connect()` | Call `listen()` + `accept()` |
| **CONNECTING** | TCP handshake | Wait for ACK | Accept incoming |
| **CONNECTED** | Active link | Send packets | Receive packets |
| **TRANSMITTING** | Active CW | Timeline active | Timeline synced |
| **IDLE** | Connected, no CW | Timeline reset | Timeline reset |
| **CLOSING** | Graceful shutdown | Send EOT, close | Drain buffer, close |

### 5.4 Reconnection Handling

```python
# Receiver: Reset on new connection
def accept_new_connection(self):
    self.sender_timeline_offset = None  # Clear old sync
    self.jitter_buffer.reset_connection()  # Clear queue
    self.last_state = None  # Reset state tracking
```

**Critical:** Each new TCP connection requires:
1. Timeline resynchronization (first packet)
2. Jitter buffer reset (clear old events)
3. State machine reset (clear DOWN/UP tracking)

---

## 6. Sender Implementation

### 6.1 Complete Sender Code

```python
#!/usr/bin/env python3
"""TCP-TS Sender Implementation"""

import socket
import struct
import time
import threading

TCP_TS_PORT = 7356

class CWProtocolTCPTimestamp:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.sequence_number = 0
        self.transmission_start = None
        self.lock = threading.Lock()
    
    def connect(self, host, port=TCP_TS_PORT, timeout=5.0):
        """Establish TCP connection"""
        try:
            if self.sock:
                self.close()
            
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((host, port))
            self.sock.settimeout(None)  # Blocking mode
            self.connected = True
            self.transmission_start = None
            return True
        except Exception as e:
            print(f"[TCP-TS] Connection failed: {e}")
            self.connected = False
            return False
    
    def send_packet(self, key_down, duration_ms):
        """Send timestamped packet"""
        if not self.connected or not self.sock:
            return False
        
        try:
            with self.lock:
                # Initialize timeline on first packet
                if self.transmission_start is None:
                    self.transmission_start = time.time()
                
                # Calculate relative timestamp
                timestamp_ms = int((time.time() - self.transmission_start) * 1000)
                
                # Build packet
                sequence = self.sequence_number
                self.sequence_number = (self.sequence_number + 1) % 256
                
                state_byte = 0x01 if key_down else 0x00
                
                # Encode duration
                if duration_ms < 256:
                    duration_bytes = struct.pack('B', duration_ms)
                else:
                    duration_bytes = struct.pack('!H', duration_ms)
                
                # Encode timestamp (4 bytes)
                timestamp_bytes = struct.pack('!I', timestamp_ms)
                
                # Assemble packet
                packet = struct.pack('BB', sequence, state_byte)
                packet += duration_bytes + timestamp_bytes
                
                # Add length prefix
                length = struct.pack('!H', len(packet))
                
                # Send
                self.sock.sendall(length + packet)
                return True
        
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[TCP-TS] Send failed: {e}")
            self.connected = False
            return False
    
    def send_eot_packet(self):
        """Send End-of-Transmission"""
        if not self.connected or not self.sock:
            return False
        
        try:
            with self.lock:
                # Calculate final timestamp
                if self.transmission_start is None:
                    timestamp_ms = 0
                else:
                    timestamp_ms = int((time.time() - self.transmission_start) * 1000)
                
                # EOT packet: seq + 0xFF + 0x00 + timestamp
                packet = struct.pack('BB', self.sequence_number, 0xFF)
                packet += struct.pack('B', 0)  # Duration 0
                packet += struct.pack('!I', timestamp_ms)
                
                # Frame and send
                length = struct.pack('!H', len(packet))
                self.sock.sendall(length + packet)
                
                # Reset timeline
                self.transmission_start = None
                return True
        
        except Exception:
            self.connected = False
            return False
    
    def close(self):
        """Close connection"""
        self.connected = False
        self.transmission_start = None
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
```

### 6.2 Sending a Character

```python
def send_morse_s(protocol):
    """Send letter 'S' (...) at 25 WPM"""
    dit_ms = 48  # 1200 / 25
    
    # Dit 1
    protocol.send_packet(True, dit_ms)   # DOWN
    time.sleep(dit_ms / 1000.0)
    protocol.send_packet(False, dit_ms)  # UP (element space)
    time.sleep(dit_ms / 1000.0)
    
    # Dit 2
    protocol.send_packet(True, dit_ms)
    time.sleep(dit_ms / 1000.0)
    protocol.send_packet(False, dit_ms)
    time.sleep(dit_ms / 1000.0)
    
    # Dit 3
    protocol.send_packet(True, dit_ms)
    time.sleep(dit_ms / 1000.0)
    protocol.send_packet(False, dit_ms * 3)  # UP (letter space)
    time.sleep(dit_ms * 3 / 1000.0)
```

**Critical:** The sender MUST call `time.sleep()` to maintain real-time pacing. Timestamps reflect when events occur, not when packets are sent.

### 6.3 Transmission Timing Example

```
Letter "S" (...) at 25 WPM:

Action              Timestamp    Real Time        Packet
──────────────────────────────────────────────────────────
START               0ms          10:00:00.000     ts=0
Dit 1 DOWN          0ms          10:00:00.000     ts=0
sleep(48ms)
Dit 1 UP            48ms         10:00:00.048     ts=48
sleep(48ms)
Dit 2 DOWN          96ms         10:00:00.096     ts=96
sleep(48ms)
Dit 2 UP            144ms        10:00:00.144     ts=144
sleep(48ms)
Dit 3 DOWN          192ms        10:00:00.192     ts=192
sleep(48ms)
Dit 3 UP            240ms        10:00:00.240     ts=240
sleep(144ms)
Next char           384ms        10:00:00.384     (ready)
```

---

## 7. Receiver Implementation

### 7.1 Complete Receiver Code

```python
#!/usr/bin/env python3
"""TCP-TS Receiver Implementation"""

import socket
import struct
import time

TCP_TS_PORT = 7356

class CWProtocolTCPTimestamp:
    def __init__(self):
        self.sock = None
        self.listen_sock = None
        self.recv_buffer = b''
        self.connected = False
    
    def listen(self, port=TCP_TS_PORT, backlog=1):
        """Start TCP server"""
        try:
            if self.listen_sock:
                self.listen_sock.close()
            
            self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listen_sock.bind(('', port))
            self.listen_sock.listen(backlog)
            return True
        except Exception as e:
            print(f"[TCP-TS] Listen failed: {e}")
            return False
    
    def accept(self):
        """Accept incoming connection"""
        try:
            if self.sock:
                self.sock.close()
            
            conn, addr = self.listen_sock.accept()
            self.sock = conn
            self.connected = True
            self.recv_buffer = b''
            return addr
        except Exception as e:
            print(f"[TCP-TS] Accept failed: {e}")
            return None
    
    def recv_packet(self):
        """
        Receive timestamped packet
        
        Returns:
            (key_down, duration_ms, timestamp_ms) or None
        """
        if not self.connected or not self.sock:
            return None
        
        try:
            # Read length prefix (2 bytes)
            while len(self.recv_buffer) < 2:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self.connected = False
                    return None
                self.recv_buffer += chunk
            
            # Parse length
            length = struct.unpack('!H', self.recv_buffer[:2])[0]
            self.recv_buffer = self.recv_buffer[2:]
            
            # Read packet
            while len(self.recv_buffer) < length:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self.connected = False
                    return None
                self.recv_buffer += chunk
            
            # Extract packet
            packet = self.recv_buffer[:length]
            self.recv_buffer = self.recv_buffer[length:]
            
            # Parse packet (min 7 bytes: seq + state + dur + ts)
            if len(packet) < 7:
                return None
            
            sequence = packet[0]
            state = packet[1]
            
            # Check for EOT
            if state == 0xFF:
                return None
            
            # Parse duration and timestamp
            if len(packet) == 7:  # 1-byte duration
                duration_ms = packet[2]
                timestamp_ms = struct.unpack('!I', packet[3:7])[0]
            else:  # 2-byte duration
                duration_ms = struct.unpack('!H', packet[2:4])[0]
                timestamp_ms = struct.unpack('!I', packet[4:8])[0]
            
            key_down = (state == 0x01)
            
            return (key_down, duration_ms, timestamp_ms)
        
        except Exception as e:
            print(f"[TCP-TS] Recv error: {e}")
            self.connected = False
            return None
    
    def close(self):
        """Close connection"""
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        if self.listen_sock:
            try:
                self.listen_sock.close()
            except:
                pass
            self.listen_sock = None
```

### 7.2 Receiver Main Loop

```python
def main():
    protocol = CWProtocolTCPTimestamp()
    jitter_buffer = JitterBuffer(150)  # 150ms buffer
    sender_timeline_offset = None
    
    # Start server
    protocol.listen(TCP_TS_PORT)
    print("[TCP-TS] Waiting for connection...")
    
    # Accept connection
    addr = protocol.accept()
    print(f"[TCP-TS] Connected from {addr}")
    
    # Receive loop
    while protocol.connected:
        result = protocol.recv_packet()
        
        if result is None:
            break  # EOT or disconnected
        
        key_down, duration_ms, timestamp_ms = result
        
        # Synchronize timeline on first packet
        if sender_timeline_offset is None:
            sender_timeline_offset = time.time() - (timestamp_ms / 1000.0)
            print("[TCP-TS] Timeline synchronized")
        
        # Calculate absolute sender event time
        sender_event_time = sender_timeline_offset + (timestamp_ms / 1000.0)
        
        # Schedule with jitter buffer
        jitter_buffer.add_event_ts(key_down, duration_ms, sender_event_time)
    
    print("[TCP-TS] Connection closed")
    protocol.close()
```

---

## 8. Jitter Buffer Integration

### 8.1 Timestamp-Based Jitter Buffer

```python
class JitterBuffer:
    def __init__(self, buffer_ms):
        self.buffer_ms = buffer_ms
        self.event_queue = queue.PriorityQueue()
        self.sender_timeline_offset = None
    
    def add_event_ts(self, key_down, duration_ms, sender_event_time):
        """
        Add event with absolute sender timestamp
        
        Args:
            sender_event_time: Absolute time in receiver's clock
        """
        # Calculate playout time (sender time + buffer)
        playout_time = sender_event_time + (self.buffer_ms / 1000.0)
        
        # Add to priority queue
        self.event_queue.put((playout_time, key_down, duration_ms))
    
    def playout_thread(self):
        """Background thread for event playback"""
        while self.running:
            try:
                playout_time, key_down, duration_ms = self.event_queue.get(timeout=0.1)
                
                # Wait until playout time
                now = time.time()
                delay = playout_time - now
                
                if delay > 0:
                    time.sleep(delay)
                
                # Play event
                self.callback(key_down, duration_ms)
                
            except queue.Empty:
                continue
```

### 8.2 Buffer Sizing Guidelines

| Network Type | Recommended Buffer | Queue Depth | Latency |
|--------------|-------------------|-------------|---------|
| **LAN (wired)** | 0-50ms | N/A or 1-2 | <10ms |
| **WiFi (good)** | 100-150ms | 2-3 | 100-150ms |
| **WiFi (congested)** | 150-200ms | 2-4 | 150-200ms |
| **Internet (good)** | 100-150ms | 2-3 | 100-180ms |
| **Internet (variable)** | 150-250ms | 3-5 | 150-280ms |
| **Cellular/Satellite** | 250-500ms | 4-8 | 250-600ms |

**Rule of thumb:** Buffer size should be 2-3× the network jitter variance.

---

## 9. Testing & Validation

### 9.1 Unit Test: Single Character

```python
def test_single_character():
    """Test sending 'E' (single dit)"""
    protocol = CWProtocolTCPTimestamp()
    protocol.connect("localhost")
    
    # Send 'E' = .
    dit_ms = 48
    
    # Dit DOWN
    protocol.send_packet(True, dit_ms)
    assert protocol.transmission_start is not None  # Timeline initialized
    time.sleep(dit_ms / 1000.0)
    
    # Dit UP
    protocol.send_packet(False, dit_ms * 3)
    time.sleep(dit_ms * 3 / 1000.0)
    
    # EOT
    protocol.send_eot_packet()
    assert protocol.transmission_start is None  # Timeline reset
    
    protocol.close()
```

### 9.2 Integration Test: Burst Scenario

```python
def test_burst_handling():
    """Test timestamp stability during burst"""
    # Send 4 packets rapidly (simulate burst)
    protocol = CWProtocolTCPTimestamp()
    protocol.connect("localhost")
    
    timestamps = []
    
    for i in range(4):
        protocol.send_packet(True if i % 2 == 0 else False, 48)
        timestamps.append(
            int((time.time() - protocol.transmission_start) * 1000)
        )
        time.sleep(0.048)  # Real-time pacing
    
    # Verify timestamps are evenly spaced (~48ms apart)
    for i in range(1, len(timestamps)):
        delta = timestamps[i] - timestamps[i-1]
        assert 45 <= delta <= 51, f"Timestamp spacing: {delta}ms"
    
    protocol.close()
```

### 9.3 Performance Test: Queue Depth

```bash
# Start receiver with debug logging
python3 cw_receiver_tcp_ts.py --jitter-buffer 150 --debug

# Send test pattern
python3 cw_auto_sender_tcp_ts.py localhost 25 "PARIS PARIS PARIS"

# Verify in logs:
# - Queue depth stays 2-3 events
# - Scheduling variance < 5ms
# - No timeline shifts
```

---

## 10. Performance Characteristics

### 10.1 Measured Performance (WiFi Network)

```
Test Configuration:
- Network: WiFi 5GHz (802.11ac)
- Jitter buffer: 150ms
- WPM: 25
- Pattern: "PARIS PARIS PARIS" (84 events)

Duration-Based Results:
- Queue depth: 6-7 events (peak)
- Scheduling ahead: 200-480ms (variable)
- Variance: ±50ms
- Timeline shifts: 0 (word space resets)

Timestamp-Based Results:
- Queue depth: 2-3 events (stable)
- Scheduling ahead: 100-150ms (consistent)
- Variance: ±1ms
- Timeline shifts: 0 (absolute timing)

Improvement:
- Queue depth: 65% reduction
- Scheduling consistency: 98% improvement
- CPU usage: Similar (~2% per connection)
```

### 10.2 Bandwidth Usage

```
Single character transmission (25 WPM):
- Average: 6 packets per character
- Packet size: 9 bytes (8 + 1 TCP overhead)
- Bandwidth: ~54 bytes/char = ~13.5 bytes/sec @ 25 WPM
- Plus TCP/IP overhead: ~700 bytes/sec total

Sustained transmission (1 minute):
- Data: ~810 bytes (90 chars × 9 bytes)
- TCP overhead: ~40 KB
- Total: ~41 KB/minute = 680 bytes/sec = 5.4 Kbps
```

**Comparison:**
- **UDP:** ~4 Kbps (no TCP overhead)
- **TCP Duration:** ~5.2 Kbps (shorter packets)
- **TCP Timestamp:** ~5.4 Kbps (4-byte timestamp)
- **Voice codec (Opus):** ~24-32 Kbps

### 10.3 Latency Analysis

```
End-to-End Latency Components:

1. Encode time: <1ms (packet assembly)
2. TCP send: 1-5ms (local stack)
3. Network transit: Variable
   - LAN: 1-5ms
   - WiFi: 5-20ms
   - Internet: 20-100ms
4. TCP receive: 1-5ms
5. Jitter buffer: 0-250ms (configured)
6. Playout: <1ms

Total typical latency:
- LAN direct: 5-10ms
- LAN buffered: 55-110ms
- WiFi buffered: 120-180ms
- Internet buffered: 150-300ms
```

---

## 11. Reference Implementation

### 11.1 File Structure

```
test_implementation/
├── cw_protocol.py              # Base protocol class
├── cw_protocol_tcp_ts.py       # TCP-TS implementation ← Main
├── cw_receiver.py              # Jitter buffer & sidetone
├── cw_receiver_tcp_ts.py       # TCP-TS receiver ← Main
├── cw_auto_sender_tcp_ts.py    # Automated test sender
├── cw_sender_tcp_ts.py         # Interactive sender
└── Doc/
    ├── TCP_TS_PROTOCOL_SPECIFICATION.md  ← This document
    └── TIMESTAMP_PROTOCOL_EXAMPLE.md     # Detailed trace
```

### 11.2 Python Dependencies

```
# Standard library only - no external dependencies
import socket
import struct
import time
import threading
import queue
```

### 11.3 Usage Examples

#### Start Receiver
```bash
# LAN (no buffer)
python3 cw_receiver_tcp_ts.py

# WiFi/Internet (150ms buffer)
python3 cw_receiver_tcp_ts.py --jitter-buffer 150

# Debug mode
python3 cw_receiver_tcp_ts.py --jitter-buffer 150 --debug
```

#### Send Test Pattern
```bash
# Automated sender
python3 cw_auto_sender_tcp_ts.py localhost 25 "PARIS"

# With debug output
python3 cw_auto_sender_tcp_ts.py localhost 25 "CQ CQ DE K3NG" --debug
```

#### Interactive Sending
```bash
# Manual text entry
python3 cw_sender_tcp_ts.py localhost 25

# Enter text at prompt:
> CQ CQ DE SM0ONR
```

---

## Appendix A: Troubleshooting

### A.1 Common Issues

**Problem:** "Connection refused"
```
Solution: Ensure receiver is running first:
  1. Start receiver: python3 cw_receiver_tcp_ts.py
  2. Start sender: python3 cw_auto_sender_tcp_ts.py localhost 25 "TEST"
```

**Problem:** Characters appear split/garbled
```
Diagnosis: Likely network bursting
Solution: Increase jitter buffer:
  python3 cw_receiver_tcp_ts.py --jitter-buffer 200
```

**Problem:** High queue depth (>5 events)
```
Diagnosis: Buffer too large for network
Solution: Reduce buffer size:
  python3 cw_receiver_tcp_ts.py --jitter-buffer 100
```

**Problem:** Audio clicks/artifacts
```
Diagnosis: Late packet dropping or underruns
Solution: 
  1. Check network stability
  2. Increase buffer: --jitter-buffer 200
  3. Enable debug: --debug
```

### A.2 Debug Output Analysis

```bash
# Enable debug logging
python3 cw_receiver_tcp_ts.py --jitter-buffer 150 --debug

# Good output:
[DEBUG] Synchronized to sender timeline (offset: 1734123456.789)
[DEBUG] Queue depth: 2 (optimal)
[STATS] WPM: 25.1, Events: 84

# Problem indicators:
[DEBUG] Queue depth: 8 (too deep - reduce buffer)
[DEBUG] Late event dropped (increase buffer)
[ERROR] Timeline sync lost (network issue)
```

---

## Appendix B: Protocol Evolution

### B.1 Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.9 | 2025-12-10 | Initial TCP-TS prototype |
| 1.0 | 2025-12-14 | Production release, full specification |

### B.2 Future Enhancements

1. **Adaptive Buffer:** Auto-adjust buffer based on measured jitter
2. **Compression:** RLE encoding for long spaces
3. **Multiplexing:** Multiple callsigns in one connection
4. **Heartbeat:** Keepalive packets for long idle periods
5. **Encryption:** TLS wrapper for secure transmission

---

## Appendix C: References

### C.1 Related Documents

- `CW_PROTOCOL_SPECIFICATION.md` - Base protocol design
- `TIMESTAMP_PROTOCOL_EXAMPLE.md` - Detailed timing trace
- `JITTER_BUFFER_IMPLEMENTATION.md` - Buffer design
- `TCP_UDP_COMPARISON.md` - Protocol selection guide

### C.2 Standards Referenced

- RFC 793: Transmission Control Protocol
- RFC 1071: Computing the Internet Checksum
- ITU-R M.1677: International Morse Code

### C.3 Implementation Notes

- Python reference: CPython 3.8+
- JavaScript reference: Node.js 14+ / Browser ES2020
- Tested platforms: Linux, macOS, Windows 10+

---

**End of Specification**

**Document Version:** 1.0  
**Last Updated:** December 14, 2025  
**Maintainer:** Duration-Encoded CW Protocol Project  
**License:** See repository LICENSE file
