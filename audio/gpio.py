#!/usr/bin/env python3
"""
GPIO Keyer - Output CW keying via Raspberry Pi GPIO
"""

import sys

# GPIO support (optional, for Raspberry Pi)
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False


class GPIOKeyer:
    """Output CW keying via Raspberry Pi GPIO pin"""
    
    def __init__(self, pin=17, active_high=True):
        """
        Initialize GPIO output
        
        Args:
            pin: BCM GPIO pin number (default 17 = physical pin 11)
            active_high: True = key-down is HIGH, False = key-down is LOW
        """
        if not GPIO_AVAILABLE:
            print("ERROR: RPi.GPIO not available")
            print("Install with: sudo apt install -y python3-rpi.gpio")
            print("or: pip3 install RPi.GPIO")
            sys.exit(1)
        
        self.pin = pin
        self.active_high = active_high
        self.key_down = False
        
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
        GPIO.setwarnings(False)
        GPIO.setup(self.pin, GPIO.OUT)
        
        # Initialize to key-up state
        self.set_key_state(False)
        
        print(f"GPIO keyer initialized on BCM pin {self.pin}")
        print(f"Key-down = {'HIGH' if active_high else 'LOW'}")
    
    def set_key_state(self, key_down):
        """Set key state (True = down/transmit, False = up/idle)"""
        self.key_down = key_down
        
        if self.active_high:
            GPIO.output(self.pin, GPIO.HIGH if key_down else GPIO.LOW)
        else:
            GPIO.output(self.pin, GPIO.LOW if key_down else GPIO.HIGH)
    
    def cleanup(self):
        """Release GPIO resources"""
        self.set_key_state(False)  # Ensure key is up
        GPIO.cleanup()
