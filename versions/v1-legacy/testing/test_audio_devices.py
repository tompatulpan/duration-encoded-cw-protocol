#!/usr/bin/env python3
"""Test which audio device is actually playing sound"""

import pyaudio
import numpy as np
import time

audio = pyaudio.PyAudio()

print("Testing each output device with a beep...\n")

for i in range(audio.get_device_count()):
    info = audio.get_device_info_by_index(i)
    if info['maxOutputChannels'] > 0:
        print(f"\n{'='*60}")
        print(f"Testing device {i}: {info['name']}")
        print(f"  Channels: {info['maxOutputChannels']}")
        print(f"  Sample rate: {info['defaultSampleRate']}")
        print(f"{'='*60}")
        
        try:
            # Open stream on this specific device
            stream = audio.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=48000,
                output=True,
                output_device_index=i,
                frames_per_buffer=128
            )
            
            print("✓ Stream opened, playing 700Hz tone for 1 second...")
            print("  (If you hear a beep, this is the right device!)")
            
            # Generate and play 1 second of 700Hz tone
            phase = 0.0
            for _ in range(int(48000 / 128)):  # 1 second worth of chunks
                samples = np.zeros(128, dtype=np.float32)
                for j in range(128):
                    samples[j] = 0.5 * np.sin(2.0 * np.pi * phase)
                    phase += 700.0 / 48000.0
                    if phase >= 1.0:
                        phase -= 1.0
                stream.write(samples.tobytes())
            
            stream.stop_stream()
            stream.close()
            print("✓ Test complete")
            
        except Exception as e:
            print(f"✗ Failed: {e}")
        
        input("Press Enter to test next device (or Ctrl+C to stop)...")

audio.terminate()
print("\nDone! Use the device number that made sound in cw_receiver.py")
