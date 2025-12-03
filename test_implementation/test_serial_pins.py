#!/usr/bin/env python3
"""
Test serial port control lines to diagnose keyer connections

This tool displays the real-time state of serial port control lines.
Use it to verify which paddle/contact is mapped to which line (CTS, DSR, etc).
Typical mapping:
  - CTS: Dit paddle
  - DSR: Dah paddle

Instructions:
  1. Connect your keyer to the serial port (e.g., /dev/ttyUSB0).
  2. Run: python3 test_serial_pins.py /dev/ttyUSB0
  3. Touch your paddles and watch the state change.
  4. Press Ctrl+C to exit.

If a line is always True, it may indicate a wiring or adapter issue.
"""
import serial
import time
import sys

if len(sys.argv) < 2:
    print("Usage: python3 test_serial_pins.py /dev/ttyUSB0")
    sys.exit(1)

port = sys.argv[1]

try:
    ser = serial.Serial(
        port=port,
        baudrate=9600,
        timeout=0
    )
    
    print(f"Serial port {port} opened")
    print("Monitoring control lines (press Ctrl+C to exit)")
    print("Touch paddle contacts to see changes:")
    print()
    print("Line | State | Notes")
    print("-----|-------|----------------------------------------------")
    
    while True:
        print(f"CTS  | {ser.cts:5} | Usually dit paddle")
        print(f"DSR  | {ser.dsr:5} | Usually dah paddle")
        print(f"RI   | {ser.ri:5}  | Ring Indicator (rarely used)")
        print(f"CD   | {ser.cd:5}  | Carrier Detect (rarely used)")
        print()
        time.sleep(0.05)
        # Clear screen
        print("\033[5A", end='')
        
except KeyboardInterrupt:
    print("\n\nExiting...")
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'ser' in locals():
        ser.close()
