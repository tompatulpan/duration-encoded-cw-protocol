# Jitter Buffer Configuration Guide

## What is a Jitter Buffer?

When transmitting CW over the internet, network delays vary randomly (jitter). This causes:
- Uneven timing between dits and dahs
- Audible "stuttering" in the sidetone
- Incorrect WPM perception

A **jitter buffer** solves this by:
1. Holding incoming packets for a short time (50-200ms)
2. Playing them back at the correct timing
3. Smoothing out network variations

## Usage

### LAN/Local Testing (No Buffer Needed)
```bash
python3 cw_receiver.py
```
- Direct playout with minimal latency
- Perfect for local network testing

### Internet/WAN Use (Buffer Recommended)
```bash
python3 cw_receiver.py --jitter-buffer 100
```
- Adds 100ms of intentional delay
- Smooths out internet jitter
- Recommended range: 50-200ms

## Buffer Size Selection

| Buffer Size | Use Case | Trade-off |
|------------|----------|-----------|
| 0ms (disabled) | LAN, localhost | Minimal latency, sensitive to jitter |
| 50ms | Fast internet, low jitter | Lower latency, some protection |
| 100ms | Standard internet | **Recommended balance** |
| 150-200ms | Poor connection, high jitter | Higher latency, maximum smoothing |
| >200ms | Extreme jitter only | Noticeable delay in QSO |

## Testing the Jitter Buffer

### Step 1: Test WITHOUT Buffer
```bash
# Terminal 1: Receiver (no buffer)
python3 cw_receiver.py

# Terminal 2: Jitter test sender
python3 test_jitter_buffer.py --jitter 50
```

**Expected result:** Uneven timing, audible variations

### Step 2: Test WITH Buffer
```bash
# Terminal 1: Receiver (with 100ms buffer)
python3 cw_receiver.py --jitter-buffer 100

# Terminal 2: Jitter test sender
python3 test_jitter_buffer.py --jitter 50
```

**Expected result:** Smooth, consistent timing

## Internet Testing

### Sender Side
```bash
# No changes needed - senders don't buffer
python3 cw_interactive_sender.py <remote_ip> 7355
```

### Receiver Side
```bash
# Use jitter buffer for internet reception
python3 cw_receiver.py --jitter-buffer 100
```

### Port Forwarding Required
Receiver must forward UDP port 7355 through router:
1. Router admin → Port Forwarding
2. Protocol: UDP
3. External Port: 7355
4. Internal IP: Your computer's LAN IP
5. Internal Port: 7355

## Visual Indicators

The receiver shows jitter buffer status:

```
[████████████████████████████████████████] DOWN  60ms | Seq: 42 Pkts: 156 Lost: 0 JBuf: 3
                                                                                    ^^^^^^
                                                                        Events queued in buffer
```

- `JBuf: 0` = Buffer empty (playout caught up)
- `JBuf: 1-5` = Normal operation
- `JBuf: >10` = Network congestion or buffer too small

## Command-Line Options

```bash
python3 cw_receiver.py --help
```

Options:
- `--port 7355` - UDP port (default: 7355)
- `--jitter-buffer 100` - Buffer size in ms (default: 0/disabled)
- `--no-audio` - Disable audio sidetone (visual only)

## Troubleshooting

### Problem: Still hearing jitter with buffer enabled
**Solutions:**
- Increase buffer size: `--jitter-buffer 150`
- Check for packet loss in receiver statistics
- Test network quality with `ping -c 100 <remote_ip>`

### Problem: Noticeable delay in conversation
**Solution:**
- Reduce buffer size: `--jitter-buffer 50`
- This is expected - jitter buffer trades latency for smoothness

### Problem: Buffer frequently fills up (JBuf > 10)
**Causes:**
- Network congestion
- CPU overload on receiver
- Buffer too small for jitter level

**Solutions:**
- Increase buffer: `--jitter-buffer 150`
- Check receiver CPU usage
- Reduce sending WPM

## Technical Details

### How It Works

```
Network → [Receive] → [Jitter Buffer] → [Playout] → Sidetone
                          ↓
                    Priority Queue
                    (sorted by time)
```

1. Packets arrive with variable delays
2. Each packet timestamped on arrival
3. Added to priority queue with: `playout_time = arrival_time + buffer_ms`
4. Playout thread waits until correct time
5. Event played with original timing preserved

### Late Packet Handling

If a packet arrives >500ms late (network problems):
- Packet is dropped
- Warning printed: `[WARNING] Dropped late event (delay: 523ms)`
- Statistics continue normally

This prevents very late packets from disrupting smooth playout.

## Implementation Notes

The jitter buffer uses Python's `queue.PriorityQueue` for time-sorted storage and a separate threading for playout, ensuring audio remains smooth even under varying network conditions.

Buffer depth affects:
- **Latency:** Higher buffer = more delay
- **Jitter tolerance:** Higher buffer = smoother with poor network
- **Memory:** Negligible (queue is typically <10 events)

Choose buffer size based on your network quality and acceptable latency in QSO.
