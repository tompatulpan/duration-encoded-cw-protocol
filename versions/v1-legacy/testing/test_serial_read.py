#!/usr/bin/env python3
"""Quick test to verify serial port pin reading"""
import serial
import time
import sys

if len(sys.argv) < 2:
    port = '/dev/ttyUSB0'
else:
    port = sys.argv[1]

try:
    ser = serial.Serial(port, 9600, timeout=0.001)
    print(f"✓ Opened {port}")
    print("Press your key, you should see state changes...")
    print("CTS (dit/key): ", end='', flush=True)
    
    last_cts = None
    last_dsr = None
    
    while True:
        cts = ser.cts
        dsr = ser.dsr
        
        if cts != last_cts:
            print(f"\nCTS: {cts} ", end='', flush=True)
            last_cts = cts
        
        if dsr != last_dsr:
            print(f"\nDSR: {dsr} ", end='', flush=True)
            last_dsr = dsr
        
        time.sleep(0.01)
        
except KeyboardInterrupt:
    print("\n\nDone!")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
