# Jitter Buffer Statistics Guide

## What You'll See

The receiver now shows **network statistics** automatically every 30 packets when using jitter buffer.

## Statistics Display

```
============================================================
NETWORK STATISTICS
============================================================
Buffer size:      100ms
Latency:          125.3ms (min:98.2 max:187.5)
Jitter:           89.3ms
Timeline shifts:  12
Max queue depth:  5
Current queue:    2
Samples:          150
============================================================
```

## What Each Metric Means

### Latency
- **Average**: Typical delay from packet arrival to playout
- **Min/Max**: Range of delays experienced
- **What it tells you**: How long packets take to arrive

### Jitter
```
Jitter = Max Latency - Min Latency
```
- Measures variation in network delay
- **High jitter** (>50ms) = unstable network
- **Low jitter** (<20ms) = stable network

### Timeline Shifts
- How many times adaptive buffer pushed timeline forward
- **Many shifts** = buffer too small for your jitter
- **Few/zero shifts** = buffer size is good

### Queue Depth
- **Max**: Largest number of events waiting
- **Current**: Events in buffer right now
- **What it tells you**: Buffer utilization

## Automatic Recommendations

The receiver provides suggestions:

### "⚠️ Increase buffer to XXXms"
Your jitter is larger than buffer size.
```bash
# Example: Jitter = 120ms, Buffer = 100ms
python3 cw_receiver.py --jitter-buffer 150
```

### "⚠️ Increase buffer (many timeline shifts)"
Buffer is being exceeded frequently.
```bash
# Increase by 50-100ms
python3 cw_receiver.py --jitter-buffer 150
```

### "✓ Buffer may be larger than needed"
Jitter is much smaller than buffer - you're adding unnecessary latency.
```bash
# Reduce buffer size
python3 cw_receiver.py --jitter-buffer 50
```

### "✓ Buffer size looks good!"
Your settings are optimal for current network conditions.

## Tuning Process

### Step 1: Start with estimate
```bash
python3 cw_receiver.py --jitter-buffer 100
```

### Step 2: Send test transmission
```bash
# From sender
python3 cw_auto_sender.py <receiver_ip> 30 "CQ CQ CQ DE SM0ONR SM0ONR K"
```

### Step 3: Read statistics
Look at the display after ~30 packets received.

### Step 4: Adjust based on recommendations
- If "increase buffer" → try +50ms
- If "buffer too large" → try -50ms  
- If "looks good" → you're done!

### Step 5: Test again
Repeat until statistics show optimal settings.

## Interpreting Results

### Example 1: Buffer Too Small
```
Jitter:           145ms
Timeline shifts:  23
Recommendation: Increase buffer to 218ms
```
**Action**: Use `--jitter-buffer 200`

### Example 2: Buffer Too Large
```
Jitter:           35ms
Timeline shifts:  0
Max queue depth:  1
Recommendation: Buffer may be larger than needed - try 70ms
```
**Action**: Use `--jitter-buffer 70`

### Example 3: Optimal
```
Jitter:           75ms
Timeline shifts:  2
Max queue depth:  4
Recommendation: Buffer size looks good!
```
**Action**: Keep current settings

## Advanced: Understanding Timeline Shifts

Timeline shifts happen when packets arrive later than expected:

```
Event should play at: T+2.000s
Event arrives at:     T+2.150s (150ms late!)
→ Timeline shifts forward 150ms
→ Shift counter increments
```

**Ideal**: 0-5 shifts per transmission
**Acceptable**: 5-15 shifts  
**Too many**: >15 shifts = increase buffer

## Real-World Examples

### Good Internet (Low Jitter)
```
Latency: 45ms (min:40 max:55)
Jitter: 15ms
Shifts: 0
Buffer: 50ms → Perfect!
```

### Standard Internet
```
Latency: 125ms (min:95 max:180)
Jitter: 85ms
Shifts: 3
Buffer: 100ms → Good balance
```

### Poor Internet (High Jitter)
```
Latency: 220ms (min:150 max:350)
Jitter: 200ms
Shifts: 34
Buffer: 150ms → Need 250ms
```

## Tips

1. **Test during different times** - jitter varies by network load
2. **Test with different WPM** - higher WPM = more sensitive to jitter
3. **Lower buffer = less latency** but requires better network
4. **Higher buffer = more forgiving** but adds delay to QSO

## What's Normal?

| Network Type | Jitter | Buffer | Shifts |
|--------------|--------|--------|--------|
| LAN | <5ms | 0ms | 0 |
| Good broadband | 10-30ms | 50ms | 0-2 |
| Standard internet | 30-80ms | 100ms | 2-10 |
| Poor connection | 80-150ms | 150-200ms | 10-20 |
| Problematic | >150ms | 200-300ms | >20 |

---

**Goal**: Find the **minimum buffer** that gives **zero or few timeline shifts** for your network.
