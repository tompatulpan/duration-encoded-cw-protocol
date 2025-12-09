# FEC Bug Fixes - December 9, 2025

## Issues Found

### 1. "Invalid state: got UP/DOWN twice in a row"
**Cause:** FEC decoder was returning ALL packets in a block (including already-received ones), causing duplicate event processing.

**Symptom:**
```
[ERROR] Invalid state: got UP twice in a row (error #1)
[ERROR] Invalid state: got DOWN twice in a row (error #2)
```

### 2. "FEC Recovered 9 packets"
**Cause:** FEC decoder returned all packets in the block, not just the recovered ones.

**Expected:** "Recovered 1-3 packets" (only the lost ones)
**Got:** "Recovered 8-9 packets" (all packets in block)

### 3. Duplicate Packet Processing
**Cause:** Packets were added to FEC decoder AFTER being processed, and FEC decoder was called twice (once for FEC packets, once for data packets).

## Fixes Applied

### Fix 1: Track Received vs Recovered Packets

**File:** `cw_protocol_fec.py`

Added `received_mask` to track which positions were actually received:

```python
self.blocks[block_id] = {
    'data': [None] * CWProtocolFEC.FEC_BLOCK_SIZE,
    'fec': [],
    'complete': False,
    'received_mask': set()  # <-- NEW: Track actually received positions
}
```

When a data packet arrives, mark it as received:
```python
self.blocks[block_id]['data'][position] = parsed_packet
self.blocks[block_id]['received_mask'].add(position)  # <-- NEW
```

### Fix 2: Only Return Recovered Packets

**File:** `cw_protocol_fec.py`

Modified `_try_decode_block()` to only return packets that were NOT already received:

```python
# Return ONLY packets that were NOT already received
recovered = []
for pos in range(CWProtocolFEC.FEC_BLOCK_SIZE):
    if block['data'][pos] is not None and pos not in block['received_mask']:
        recovered.append(block['data'][pos])
```

If all packets received, return empty list (no duplicates):
```python
if missing == 0:
    block['complete'] = True
    return []  # <-- Changed from returning all packets
```

### Fix 3: Process Packets Only Once

**File:** `cw_receiver_fec.py`

Moved FEC decoder call to BEFORE packet processing, and call it for ALL packets:

**Before:**
```python
# Wrong: FEC decoder called AFTER processing, and twice
if parsed.get('is_fec', False):
    if self.fec_decoder:
        recovered = self.fec_decoder.add_packet(parsed)
    continue

# ... process events ...

if self.fec_decoder and not parsed.get('is_fec', False):
    self.fec_decoder.add_packet(parsed)  # Called again!
```

**After:**
```python
# Correct: FEC decoder called ONCE, BEFORE processing
if self.fec_decoder:
    recovered = self.fec_decoder.add_packet(parsed)
    if recovered:
        # Process only truly recovered packets
        ...

# Skip further processing for FEC packets
if parsed.get('is_fec', False):
    self.fec_packet_count += 1
    continue

# Process regular data packets normally
...
```

## Testing

Test with packet loss to verify fixes:

```bash
# Terminal 1
python3 cw_receiver_fec.py --jitter-buffer 200

# Terminal 2
python3 cw_sender_fec_sim.py localhost 25 "PARIS PARIS" --loss 0.2
```

**Expected output:**
- No "Invalid state" errors
- "Recovered X packets" where X ≤ 3 (actual lost packets)
- No duplicate events
- Clean state transitions (UP → DOWN → UP → DOWN)

## Remaining Work

### Full Reed-Solomon Decoding

Currently, FEC decoder identifies lost packets but doesn't actually reconstruct them:

```python
# TODO: Implement full Reed-Solomon decoding with erasures
# This requires:
# 1. Reconstruct block data from received packets
# 2. Mark erasure positions
# 3. Call rs.decode() with erasure positions
# 4. Extract recovered packet data
```

**Next steps:**
1. Serialize all 10 data packets into byte array
2. Append FEC parity bytes
3. Mark missing positions as erasures
4. Use `reedsolo` to decode with erasures
5. Deserialize recovered bytes back to packets

## Summary

✅ **Fixed:** Duplicate packet processing
✅ **Fixed:** "Invalid state" errors  
✅ **Fixed:** Incorrect recovery count
⚙️ **TODO:** Implement actual Reed-Solomon decoding

The FEC framework is now working correctly - it tracks packets properly and identifies losses. The final step is implementing the actual RS decode logic to reconstruct lost packets.
