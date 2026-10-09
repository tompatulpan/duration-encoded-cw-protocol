# Event Batching Protocol - Implementation Proposal

## Overview

Currently, each CW event (tone_start/tone_end) is sent as an individual WebSocket message. This proposal introduces **event batching** to improve network efficiency and provide natural error recovery.

## Current Architecture

**Per-Event Transmission:**
```
Character "S" (3 dits):
- Message 1: {type: 'cw_event', event: 'tone_start', duration: 0}
- Message 2: {type: 'cw_event', event: 'tone_end', duration: 48}
- Message 3: {type: 'cw_event', event: 'tone_start', duration: 0}
- Message 4: {type: 'cw_event', event: 'tone_end', duration: 48}
- Message 5: {type: 'cw_event', event: 'tone_start', duration: 0}
- Message 6: {type: 'cw_event', event: 'tone_end', duration: 48}

Total: 6 WebSocket messages
```

**Issues:**
- High protocol overhead (JSON encoding + WebSocket framing per event)
- Many small network packets (below optimal Ethernet frame size of 46+ bytes)
- No built-in error recovery
- High CPU usage for encoding/decoding

## Proposed Architecture

**Batched Transmission:**
```json
{
  "type": "cw_batch",
  "sender": "SM0ONR",
  "sequence": 42,
  "timestamp_base": 1733234567.123,
  "events": [
    {"event": "tone_end", "duration": 48, "offset_ms": 0},
    {"event": "tone_end", "duration": 144, "offset_ms": 53},
    {"event": "tone_end", "duration": 48, "offset_ms": 250}
  ]
}
```

**Features:**
- Multiple events in single WebSocket message
- Sequence number for detecting packet loss
- Base timestamp + millisecond offsets (reduces redundancy)
- Natural error containment (one corrupted batch ≠ sync loss)

## Implementation Details

### Python Sender (cw_protocol.py)

```python
class CWProtocol:
    def __init__(self):
        self.sequence_number = 0
        self.event_batch = []
        self.batch_start_time = None
        self.batch_timeout_ms = 30  # Adaptive: send after 30ms or 10 events
        self.max_batch_size = 10
        
    async def queue_event(self, event_type, duration_ms):
        """Queue event for batching"""
        current_time = time.time()
        
        # Initialize batch if empty
        if not self.event_batch:
            self.batch_start_time = current_time
        
        # Calculate offset from batch start
        offset_ms = int((current_time - self.batch_start_time) * 1000)
        
        self.event_batch.append({
            'event': event_type,
            'duration': duration_ms,
            'offset_ms': offset_ms
        })
        
        # Send if batch full or timeout reached
        if (len(self.event_batch) >= self.max_batch_size or 
            offset_ms >= self.batch_timeout_ms):
            await self.flush_batch()
    
    async def flush_batch(self):
        """Send accumulated batch"""
        if not self.event_batch:
            return
            
        batch_packet = {
            'type': 'cw_batch',
            'sender': self.callsign,
            'sequence': self.sequence_number,
            'timestamp_base': self.batch_start_time,
            'events': self.event_batch
        }
        
        await self.send_packet(batch_packet)
        
        self.sequence_number += 1
        self.event_batch = []
        self.batch_start_time = None
```

### JavaScript Receiver (room.js)

```javascript
class RoomController {
    constructor() {
        this.lastSequence = new Map();  // peerId -> last sequence
        this.lostBatches = new Map();   // peerId -> count
    }
    
    _handleCWBatch(peerId, callsign, batch) {
        // Check sequence number for packet loss
        const lastSeq = this.lastSequence.get(peerId) || -1;
        const expectedSeq = lastSeq + 1;
        
        if (batch.sequence !== expectedSeq) {
            const lost = batch.sequence - expectedSeq;
            console.warn(`Lost ${lost} batch(es) from ${callsign}`);
            
            // Track packet loss statistics
            const currentLoss = this.lostBatches.get(peerId) || 0;
            this.lostBatches.set(peerId, currentLoss + lost);
        }
        
        this.lastSequence.set(peerId, batch.sequence);
        
        // Process each event in batch
        const baseTimestamp = batch.timestamp_base;
        
        for (const evt of batch.events) {
            const eventTimestamp = baseTimestamp + (evt.offset_ms / 1000);
            
            // Feed to jitter buffer
            this._handleRemoteCWEvent(
                peerId, 
                callsign, 
                evt.event, 
                evt.duration,
                eventTimestamp
            );
        }
    }
}
```

### Cloudflare Worker (signaling.js)

```javascript
// Simply relay batches to all room members
async handleCWBatch(ws, batch) {
    const room = this.rooms.get(ws.roomId);
    if (!room) return;
    
    // Broadcast to all except sender
    room.members.forEach((member) => {
        if (member !== ws) {
            member.send(JSON.stringify(batch));
        }
    });
}
```

## Error Recovery Mechanism

### How It Works in Practice

**Scenario 1: Normal Operation**
```
Sender:   Batch#1 → Batch#2 → Batch#3 → Batch#4
Receiver: Seq 1    Seq 2     Seq 3     Seq 4  ✓ All received
```

**Scenario 2: Single Batch Lost**
```
Sender:   Batch#1 → Batch#2 → [LOST] → Batch#4
Receiver: Seq 1    Seq 2     (gap!)    Seq 4
          ↓
          Detect: Expected seq 3, got seq 4
          Lost events: ~3-10 (one batch worth)
          Recovery: Jitter buffer continues with next batch
          Impact: Brief audio gap, decoder may miss 1 character
```

**Scenario 3: Consecutive Batches Lost**
```
Sender:   Batch#1 → [LOST] → [LOST] → Batch#4
Receiver: Seq 1    (gap!)   (gap!)    Seq 4
          ↓
          Detect: Expected seq 2, got seq 4
          Lost events: ~6-20 (two batches)
          Recovery: Jitter buffer drains, restarts on seq 4
          Impact: Word-level gap, decoder resets
```

### Error Recovery Benefits

1. **Graceful Degradation**
   - Single lost batch = small audio gap (30-50ms)
   - Not catastrophic like losing sync in streaming protocol

2. **Automatic Resync**
   - Sequence numbers detect loss immediately
   - Next valid batch continues operation
   - No manual intervention needed

3. **Statistics Tracking**
   - Count lost batches per peer
   - Display in UI: "Connection quality: 98.5% (3 lost batches)"
   - Adaptive jitter buffer sizing based on loss rate

4. **Compared to Per-Event**
   - Per-event: Lose 1 event → decoder confused about timing
   - Batched: Lose 1 batch → clear gap, decoder understands break

### Error Correction Strategy

**Without FEC (Current Proposal):**
- Detection only (sequence numbers)
- Jitter buffer handles gaps gracefully
- Simple implementation

**With FEC (Future Enhancement):**
```json
{
  "type": "cw_batch",
  "events": [...],
  "parity": "XOR_OF_ALL_EVENTS",  // Simple parity
  "fec_type": "reed_solomon"       // Or more advanced
}
```

Benefits of FEC:
- Recover 1-2 corrupted events per batch
- Higher complexity, minimal gain (WebSocket already reliable)
- Better for UDP variant of protocol

## Adaptive Batch Timeout

```python
class AdaptiveBatcher:
    def __init__(self):
        self.base_timeout_ms = 30
        self.current_timeout_ms = 30
        self.wpm_estimate = 20
        
    def update_timeout(self, wpm):
        """Adjust timeout based on sending speed"""
        self.wpm_estimate = wpm
        
        # Fast sending (>25 WPM): shorter timeout for lower latency
        if wpm > 25:
            self.current_timeout_ms = 20
        # Slow sending (<15 WPM): longer timeout to batch more
        elif wpm < 15:
            self.current_timeout_ms = 50
        else:
            self.current_timeout_ms = 30
```

## Network Efficiency Analysis

### Packet Size Comparison

**Current (Per-Event):**
```
Per event: ~80 bytes JSON + WebSocket overhead
Character "S" (3 dits): 6 events × 80 bytes = 480 bytes
```

**Batched:**
```
Batch header: ~120 bytes
Per event: ~30 bytes (in array)
Character "S" (3 dits): 120 + (6 × 30) = 300 bytes
Savings: 37.5%
```

### Ethernet Frame Utilization

- **Minimum Ethernet frame:** 46 bytes payload
- **Current:** Many frames with <46 bytes (padded to minimum)
- **Batched:** Most frames >100 bytes (efficient)
- **Benefit:** Better frame utilization = less network overhead

### Latency Impact

**Added Latency:**
- Batch timeout: 20-50ms (adaptive)
- Jitter buffer: 300ms (already present)
- **Net impact:** +20-50ms over current

**Mitigation:**
- Flush batch on idle (no events for 20ms)
- Reduce timeout for fast sending
- Acceptable tradeoff for efficiency gains

## Pros and Cons

### Pros

✅ **Network Efficiency**
- 30-40% reduction in bandwidth usage
- Better Ethernet frame utilization
- Lower CPU for JSON encoding/decoding

✅ **Error Recovery**
- Sequence numbers detect packet loss
- Natural error containment per batch
- Jitter buffer handles gaps gracefully

✅ **Scalability**
- Less WebSocket message overhead
- Better for multi-user rooms
- Cloudflare Worker processes fewer messages

✅ **Statistics**
- Track packet loss per peer
- Display connection quality metrics
- Adaptive jitter buffer sizing

✅ **Future-Proof**
- Easy to add FEC later
- Enables UDP transport variant
- Room for protocol evolution

### Cons

❌ **Increased Latency**
- Added 20-50ms batch timeout
- May feel sluggish for fast operators
- Mitigation: Adaptive timeout based on WPM

❌ **Implementation Complexity**
- Buffering logic in sender
- Sequence tracking in receiver
- More complex debugging

❌ **Backward Compatibility**
- Need protocol version negotiation
- Must support both modes during transition
- Migration path required

❌ **Burst Traffic**
- Large batches create traffic spikes
- May stress jitter buffer
- Mitigation: Max batch size limit

❌ **Error Amplification**
- Lost batch = multiple lost events
- Worse than per-event for high loss rates
- Only benefit if loss rate <1%

## Migration Strategy

### Phase 1: Dual Protocol Support
```python
class CWProtocol:
    def __init__(self, batching_enabled=False):
        self.batching_enabled = batching_enabled
        
    async def send_event(self, event, duration):
        if self.batching_enabled:
            await self.queue_event(event, duration)
        else:
            await self.send_single_event(event, duration)
```

### Phase 2: Feature Flag in UI
- Room settings: "Enable event batching (experimental)"
- Client announces capability on join
- Worker routes accordingly

### Phase 3: Default to Batching
- Make batching default
- Keep legacy mode for compatibility
- Monitor metrics for regression

### Phase 4: Deprecate Legacy
- Remove per-event mode after 6 months
- Simplify codebase

## Performance Metrics to Track

1. **Bandwidth Usage**
   - Bytes/second per connection
   - Before/after comparison

2. **Packet Loss Rate**
   - Lost batches / total batches
   - Per-room statistics

3. **Latency Distribution**
   - P50, P95, P99 event-to-playback time
   - Impact of batch timeout

4. **CPU Usage**
   - Sender: JSON encoding time
   - Receiver: Decoding + jitter buffer

5. **User Experience**
   - Operator feedback on responsiveness
   - Audio quality reports

## Conclusion

Event batching provides significant efficiency gains with acceptable latency tradeoff. The natural error recovery from sequence numbering is a major benefit for reliability.

**Recommendation:** Implement as opt-in experimental feature, gather metrics, then make default if metrics are positive.

**Next Steps:**
1. Implement in separate git worktree
2. Add protocol version negotiation
3. Test with high packet loss simulation
4. Measure real-world performance
5. Gather user feedback
