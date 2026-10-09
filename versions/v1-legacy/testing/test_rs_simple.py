#!/usr/bin/env python3
"""
Simple test of Reed-Solomon encoding/decoding with reedsolo
"""

import reedsolo

# Test parameters
DATA_SIZE = 60  # 10 packets × 6 bytes
PARITY_SIZE = 18  # 3 packets × 6 bytes of parity

print("Reed-Solomon Encoding/Decoding Test")
print("=" * 60)

# Create RS codec
rs = reedsolo.RSCodec(PARITY_SIZE)

# Create test data (60 bytes)
original_data = bytes(range(60))
print(f"Original data: {len(original_data)} bytes")
print(f"First 12 bytes: {original_data[:12].hex()}")

# Encode
encoded = rs.encode(original_data)
print(f"\nEncoded: {len(encoded)} bytes ({len(original_data)} data + {PARITY_SIZE} parity)")
parity = encoded[DATA_SIZE:]
print(f"Parity bytes: {parity.hex()}")

# Test 1: No errors - should decode perfectly
print("\n" + "=" * 60)
print("Test 1: No errors")
decoded = rs.decode(encoded)[0]
print(f"✓ Decoded successfully: {decoded == original_data}")

# Test 2: Erase 1 packet (6 bytes) - positions 12-17
print("\n" + "=" * 60)
print("Test 2: Erase 1 packet (6 bytes at positions 12-17)")
corrupted = bytearray(encoded)
erasure_pos = list(range(12, 18))
for pos in erasure_pos:
    corrupted[pos] = 0  # Erase

print(f"Erasure positions: {erasure_pos}")
try:
    decoded = rs.decode(bytes(corrupted), erase_pos=erasure_pos)[0]
    print(f"✓ Decoded successfully: {decoded == original_data}")
    print(f"  Recovered bytes: {decoded[12:18].hex()}")
    print(f"  Original bytes:  {original_data[12:18].hex()}")
except Exception as e:
    print(f"✗ Decode failed: {e}")

# Test 3: Erase 2 packets (12 bytes) - positions 0-5 and 24-29
print("\n" + "=" * 60)
print("Test 3: Erase 2 packets (12 bytes)")
corrupted = bytearray(encoded)
erasure_pos = list(range(0, 6)) + list(range(24, 30))
for pos in erasure_pos:
    corrupted[pos] = 0

print(f"Erasure positions: {erasure_pos}")
try:
    decoded = rs.decode(bytes(corrupted), erase_pos=erasure_pos)[0]
    print(f"✓ Decoded successfully: {decoded == original_data}")
    print(f"  Recovered bytes [0:6]:  {decoded[0:6].hex()}")
    print(f"  Original bytes [0:6]:   {original_data[0:6].hex()}")
    print(f"  Recovered bytes [24:30]: {decoded[24:30].hex()}")
    print(f"  Original bytes [24:30]:  {original_data[24:30].hex()}")
except Exception as e:
    print(f"✗ Decode failed: {e}")

# Test 4: Erase 3 packets (18 bytes) - maximum capacity
print("\n" + "=" * 60)
print("Test 4: Erase 3 packets (18 bytes) - at FEC limit")
corrupted = bytearray(encoded)
erasure_pos = list(range(0, 6)) + list(range(12, 18)) + list(range(36, 42))
for pos in erasure_pos:
    corrupted[pos] = 0

print(f"Erasure positions: {erasure_pos} ({len(erasure_pos)} bytes)")
try:
    decoded = rs.decode(bytes(corrupted), erase_pos=erasure_pos)[0]
    print(f"✓ Decoded successfully: {decoded == original_data}")
except Exception as e:
    print(f"✗ Decode failed: {e}")

# Test 5: Erase 4 packets (24 bytes) - exceeds capacity
print("\n" + "=" * 60)
print("Test 5: Erase 4 packets (24 bytes) - exceeds FEC capacity")
corrupted = bytearray(encoded)
erasure_pos = list(range(0, 6)) + list(range(12, 18)) + list(range(24, 30)) + list(range(36, 42))
for pos in erasure_pos:
    corrupted[pos] = 0

print(f"Erasure positions: {erasure_pos} ({len(erasure_pos)} bytes)")
try:
    decoded = rs.decode(bytes(corrupted), erase_pos=erasure_pos)[0]
    print(f"✓ Decoded successfully: {decoded == original_data}")
except Exception as e:
    print(f"✗ Decode failed (expected): {e}")

print("\n" + "=" * 60)
print("Summary: RS codec with 18 parity bytes can correct up to 18 erased bytes")
