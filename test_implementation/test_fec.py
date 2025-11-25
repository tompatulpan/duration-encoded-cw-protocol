#!/usr/bin/env python3
"""
Test tool for FEC (Forward Error Correction)

Demonstrates packet loss recovery using:
1. Simple duplication
2. Interpolation for missing packets

Usage:
  python3 test_fec.py [host] [loss_percent] [fec_mode]
  
  loss_percent: 0-50 (percent of packets to drop)
  fec_mode: none, duplicate, interpolate
"""

import sys
import socket
import time
import random
from cw_protocol import CWProtocol
from cw_fec import CWProtocolFEC, FECReceiver

def simulate_lossy_channel(packets, loss_percent):
    """
    Simulate packet loss
    
    Args:
        packets: list of packets to send
        loss_percent: 0-100 percent loss rate
        
    Returns: list of packets that "survived"
    """
    survived = []
    dropped = []
    
    for i, pkt in enumerate(packets):
        if random.random() * 100 > loss_percent:
            survived.append(pkt)
        else:
            dropped.append(i)
    
    return survived, dropped

def test_no_fec(loss_percent):
    """Test without FEC"""
    print(f"\n{'='*60}")
    print(f"TEST: No FEC, {loss_percent}% packet loss")
    print(f"{'='*60}")
    
    proto = CWProtocol()
    
    # Create test sequence: "SOS" pattern
    # S = dit dit dit (3 packets)
    # O = dah dah dah (3 packets)
    # S = dit dit dit (3 packets)
    test_events = [
        (True, 60),   # dit down
        (False, 60),  # dit up
        (True, 60),   # dit down
        (False, 60),  # dit up
        (True, 60),   # dit down
        (False, 180), # letter space
        (True, 180),  # dah down
        (False, 60),  # dah up
        (True, 180),  # dah down
        (False, 60),  # dah up
        (True, 180),  # dah down
        (False, 180), # letter space
        (True, 60),   # dit down
        (False, 60),  # dit up
        (True, 60),   # dit down
        (False, 60),  # dit up
        (True, 60),   # dit down
        (False, 60),  # final up
    ]
    
    # Create packets
    packets = []
    for key_down, duration in test_events:
        pkt = proto.create_packet(key_down, duration)
        packets.append(pkt)
    
    print(f"Created {len(packets)} packets")
    
    # Simulate loss
    survived, dropped = simulate_lossy_channel(packets, loss_percent)
    
    print(f"Survived: {len(survived)}/{len(packets)} packets")
    print(f"Lost: {len(dropped)} packets at positions {dropped[:5]}{'...' if len(dropped) > 5 else ''}")
    
    loss_rate = (len(dropped) / len(packets)) * 100
    print(f"Actual loss rate: {loss_rate:.1f}%")
    
    return len(survived), len(packets)

def test_duplicate_fec(loss_percent, copies=2):
    """Test with duplication FEC"""
    print(f"\n{'='*60}")
    print(f"TEST: Duplication FEC ({copies}x), {loss_percent}% packet loss")
    print(f"{'='*60}")
    
    proto = CWProtocolFEC(fec_mode='duplicate', fec_param=copies)
    receiver = FECReceiver(fec_mode='duplicate')
    
    # Same test sequence
    test_events = [
        (True, 60), (False, 60), (True, 60), (False, 60), (True, 60), (False, 180),
        (True, 180), (False, 60), (True, 180), (False, 60), (True, 180), (False, 180),
        (True, 60), (False, 60), (True, 60), (False, 60), (True, 60), (False, 60),
    ]
    
    # Create packets with FEC
    all_packets = []
    for key_down, duration in test_events:
        pkts = proto.create_packet_with_fec(key_down, duration)
        all_packets.extend(pkts)
    
    print(f"Created {len(all_packets)} packets ({len(test_events)} events × {copies} copies)")
    
    # Simulate loss
    survived, dropped = simulate_lossy_channel(all_packets, loss_percent)
    
    print(f"Survived: {len(survived)}/{len(all_packets)} packets")
    print(f"Lost: {len(dropped)} packets")
    
    # Process through receiver (deduplicates)
    unique_received = []
    for pkt in survived:
        processed = receiver.process_packet(pkt)
        if processed:
            unique_received.append(processed)
    
    print(f"Unique events received: {len(unique_received)}/{len(test_events)}")
    
    recovery_rate = (len(unique_received) / len(test_events)) * 100
    print(f"Recovery rate: {recovery_rate:.1f}%")
    
    return len(unique_received), len(test_events)

def test_interpolation(loss_percent):
    """Test with interpolation"""
    print(f"\n{'='*60}")
    print(f"TEST: Interpolation, {loss_percent}% packet loss")
    print(f"{'='*60}")
    
    proto = CWProtocol()
    receiver = FECReceiver(fec_mode='none')
    
    # Same test sequence
    test_events = [
        (True, 60), (False, 60), (True, 60), (False, 60), (True, 60), (False, 180),
        (True, 180), (False, 60), (True, 180), (False, 60), (True, 180), (False, 180),
        (True, 60), (False, 60), (True, 60), (False, 60), (True, 60), (False, 60),
    ]
    
    # Create packets
    packets = []
    for key_down, duration in test_events:
        pkt = proto.create_packet(key_down, duration)
        packets.append(pkt)
    
    print(f"Created {len(packets)} packets")
    
    # Simulate loss
    survived, dropped_indices = simulate_lossy_channel(packets, loss_percent)
    
    print(f"Survived: {len(survived)}/{len(packets)} packets")
    print(f"Lost: {len(dropped_indices)} packets")
    
    # Process and detect gaps
    received_packets = []
    last_seq = -1
    interpolated_count = 0
    
    for pkt in survived:
        parsed = proto.parse_packet(pkt)
        if not parsed:
            continue
        
        seq = parsed['sequence']
        
        # Detect gap
        if last_seq >= 0 and seq > last_seq + 1:
            gap_size = seq - last_seq - 1
            print(f"  Gap detected: missing {gap_size} packet(s) between seq {last_seq} and {seq}")
            
            # Try to interpolate
            if gap_size <= 2 and len(received_packets) > 0:
                interpolated = receiver.interpolate_missing(
                    last_seq, seq, 
                    [p for p in received_packets[-3:]], 
                    pkt
                )
                if interpolated:
                    print(f"    → Interpolated {len(interpolated)} packet(s)")
                    received_packets.extend(interpolated)
                    interpolated_count += len(interpolated)
        
        received_packets.append(pkt)
        last_seq = seq
    
    total_recovered = len(survived) + interpolated_count
    recovery_rate = (total_recovered / len(packets)) * 100
    
    print(f"Total recovered: {total_recovered}/{len(packets)} ({len(survived)} received + {interpolated_count} interpolated)")
    print(f"Recovery rate: {recovery_rate:.1f}%")
    
    return total_recovered, len(packets)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_fec.py <loss_percent> [test_mode]")
        print("  loss_percent: 0-50 (packet loss percentage)")
        print("  test_mode: all, none, duplicate, interpolate (default: all)")
        sys.exit(1)
    
    loss_percent = float(sys.argv[1])
    test_mode = sys.argv[2] if len(sys.argv) > 2 else 'all'
    
    print(f"\n{'='*60}")
    print(f"FEC PACKET LOSS RECOVERY TEST")
    print(f"{'='*60}")
    print(f"Simulated packet loss: {loss_percent}%")
    print(f"Test pattern: SOS (18 packets)")
    
    results = {}
    
    if test_mode in ['all', 'none']:
        survived, total = test_no_fec(loss_percent)
        results['No FEC'] = (survived / total) * 100
    
    if test_mode in ['all', 'duplicate']:
        survived, total = test_duplicate_fec(loss_percent, copies=2)
        results['2x Duplication'] = (survived / total) * 100
        
        survived, total = test_duplicate_fec(loss_percent, copies=3)
        results['3x Duplication'] = (survived / total) * 100
    
    if test_mode in ['all', 'interpolate']:
        survived, total = test_interpolation(loss_percent)
        results['Interpolation'] = (survived / total) * 100
    
    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Simulated loss: {loss_percent}%\n")
    
    for method, recovery in sorted(results.items(), key=lambda x: x[1], reverse=True):
        print(f"  {method:20s}: {recovery:5.1f}% recovery")
    
    print(f"\n{'='*60}")

if __name__ == '__main__':
    main()
