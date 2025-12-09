# FEC Network Simulation Testing

## Quick Start

Test FEC recovery with simulated packet loss and jitter:

### Terminal 1: Start Receiver
```bash
python3 cw_receiver_fec.py
```

### Terminal 2: Test with Different Conditions

**No packet loss (baseline):**
```bash
python3 cw_sender_fec_sim.py localhost 25 "PARIS PARIS" --loss 0.0
```

**10% packet loss:**
```bash
python3 cw_sender_fec_sim.py localhost 25 "PARIS PARIS" --loss 0.1
```

**20% packet loss + 50ms jitter:**
```bash
python3 cw_sender_fec_sim.py localhost 25 "PARIS PARIS" --loss 0.2 --jitter 50
```

**30% packet loss (FEC limit):**
```bash
python3 cw_sender_fec_sim.py localhost 25 "PARIS PARIS" --loss 0.3
```

**Extreme: 25% loss + 100ms jitter + 15% reordering:**
```bash
python3 cw_sender_fec_sim.py localhost 25 "PARIS PARIS" --loss 0.25 --jitter 100 --reorder 0.15
```

## Automated Test Suite

Run all tests automatically:
```bash
./test_fec_suite.sh
```

## Understanding the Parameters

### --loss (Packet Loss Rate)
- `0.0` = No loss (0%)
- `0.1` = 10% packet loss
- `0.2` = 20% packet loss
- `0.3` = 30% packet loss (FEC recovery limit)

**FEC Recovery Capability:**
- Can recover up to **3 lost packets per 10 data packets** (30%)
- Loss > 30%: Some packets cannot be recovered

### --jitter (Network Delay Variation)
- Simulates variable network latency
- Value in milliseconds: ±X ms
- Examples:
  - `--jitter 20` = packets arrive with ±20ms variation
  - `--jitter 100` = packets arrive with ±100ms variation

### --reorder (Packet Reordering)
- Simulates out-of-order packet delivery
- `0.0` = No reordering (0%)
- `0.1` = 10% of packets arrive out of order
- Common on multi-path networks

## Expected Results

### Test Scenarios

| Loss | Jitter | Reorder | Expected Result |
|------|--------|---------|-----------------|
| 0%   | 0ms    | 0%      | Perfect (no FEC needed) |
| 5%   | 0ms    | 0%      | 100% recovery |
| 10%  | 50ms   | 0%      | 100% recovery |
| 20%  | 100ms  | 10%     | ~95% recovery |
| 30%  | 0ms    | 0%      | 100% recovery (at limit) |
| 35%  | 0ms    | 0%      | ~85% recovery (exceeds FEC) |

### Interpreting Receiver Output

```
Total data packets received: 42
Total FEC packets received: 15
Packets lost: 8
Packets recovered by FEC: 7
Packet loss rate: 16.00%
FEC recovery rate: 87.5%
```

- **Packets lost**: Actual packets that didn't arrive
- **Packets recovered**: How many FEC successfully restored
- **FEC recovery rate**: Percentage of lost packets recovered

### Success Indicators

✓ **Working well**: FEC recovery rate > 90%
⚠️ **Struggling**: FEC recovery rate 50-90%
❌ **Overwhelmed**: FEC recovery rate < 50%

## Real-World Scenarios

### Home Internet (Good)
```bash
python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.02 --jitter 10
```
2% loss, 10ms jitter - FEC easily handles this

### Cellular Data (Moderate)
```bash
python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.08 --jitter 50 --reorder 0.05
```
8% loss, 50ms jitter, 5% reordering - FEC should recover well

### Satellite/Poor Connection (Heavy)
```bash
python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.15 --jitter 150 --reorder 0.10
```
15% loss, 150ms jitter, 10% reordering - FEC at work hard

### Congested Network (Extreme)
```bash
python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.25 --jitter 200 --reorder 0.20
```
25% loss, 200ms jitter, 20% reordering - Near FEC limits

## Troubleshooting

**Problem: No audio on receiver**
- Check system volume
- Verify receiver is running with audio enabled
- Default jitter buffer (150ms) should work for most tests

**Problem: High loss rate with low --loss setting**
- This is expected - some random loss is simulated
- Run test multiple times to see average performance
- Increase jitter buffer on receiver if needed

**Problem: FEC not recovering packets**
- Check that loss rate < 30% (FEC limit)
- Ensure receiver has jitter buffer enabled (default 150ms)
- Verify reedsolo is installed: `pip3 list | grep reedsolo`

**Problem: Audio glitches/clicks**
- Increase receiver jitter buffer: `--jitter-buffer 200`
- Reduce sender jitter: `--jitter 50` instead of 100+
- This is normal with extreme network conditions

## Performance Tips

1. **Start conservative**: Test with low loss (5-10%) first
2. **Increase gradually**: Work up to 20-30% to see FEC limits
3. **Combine factors**: Test loss + jitter + reordering together
4. **Multiple runs**: Results vary due to randomness
5. **Monitor receiver**: Watch recovery statistics

## Next Steps

After testing:
1. Adjust FEC block size for your needs (edit `cw_protocol_fec.py`)
2. Tune jitter buffer based on your network
3. Consider adaptive FEC (adjusts redundancy based on conditions)
