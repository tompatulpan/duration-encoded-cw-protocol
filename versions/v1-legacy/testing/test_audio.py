#!/usr/bin/env python3
"""Test audio output"""

import pyaudio
import numpy as np
import time

print("Testing PyAudio...")

try:
    audio = pyaudio.PyAudio()
    
    # List audio devices
    print("\nAvailable audio devices:")
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if info['maxOutputChannels'] > 0:
            print(f"  [{i}] {info['name']} (out: {info['maxOutputChannels']} channels)")
    
    # Try to open stream
    print("\nOpening audio stream...")
    stream = audio.open(
        format=pyaudio.paFloat32,
        channels=1,
        rate=48000,
        output=True,
        frames_per_buffer=128
    )
    
    print("Stream opened successfully!")
    print("Playing 700 Hz tone for 2 seconds...")
    
    # Generate and play tone
    sample_rate = 48000
    frequency = 700
    duration = 2.0
    samples_total = int(sample_rate * duration)
    chunk_size = 128
    
    phase = 0.0
    phase_increment = frequency / sample_rate
    
    for start in range(0, samples_total, chunk_size):
        samples = np.zeros(chunk_size, dtype=np.float32)
        for i in range(chunk_size):
            samples[i] = 0.3 * np.sin(2.0 * np.pi * phase)
            phase += phase_increment
            if phase >= 1.0:
                phase -= 1.0
        
        stream.write(samples.tobytes())
    
    print("Audio test complete!")
    
    stream.stop_stream()
    stream.close()
    audio.terminate()
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
