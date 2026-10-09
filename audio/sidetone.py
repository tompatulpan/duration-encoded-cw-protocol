#!/usr/bin/env python3
"""
Sidetone Generator - Audio feedback for CW keying
"""

import threading
import math
from ctypes import *

# Audio support (optional)
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

# Suppress ALSA error messages during PyAudio initialization
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)

def py_error_handler(filename, line, function, err, fmt):
    """Suppress ALSA/JACK error messages"""
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

def suppress_alsa_messages():
    """Suppress ALSA error output during device scanning"""
    try:
        asound = cdll.LoadLibrary('libasound.so.2')
        asound.snd_lib_error_set_handler(c_error_handler)
    except:
        pass  # Not on Linux or ALSA not available


class SidetoneGenerator:
    """Generate audio sidetone with improved signal quality"""
    
    def __init__(self, frequency=600, sample_rate=48000, device_index=None):
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.volume = 0.3
        
        if not AUDIO_AVAILABLE:
            return
        
        # Initialize state BEFORE opening stream (callback needs these!)
        self.phase = 0.0
        self.key_down = False
        self.envelope = 0.0
        self.target_envelope = 0.0
        
        # Envelope shaping to prevent clicks (optimized for CW)
        self.rise_time = 0.004  # 4ms - fast, clean attack
        self.fall_time = 0.004  # 4ms - fast, clean release
        
        # Simple low-pass filter state for smoother audio
        self.filter_state = 0.0
        self.filter_alpha = 0.1  # Low-pass filter coefficient (smoother = lower value)
        
        # Pre-calculate constants for callback
        self.phase_increment = self.frequency / self.sample_rate
        self.rise_rate = 1.0 / (self.rise_time * self.sample_rate)
        self.fall_rate = 1.0 / (self.fall_time * self.sample_rate)
        self.two_pi = 2.0 * np.pi
        
        # Now open audio stream (use blocking mode - callback mode has PulseAudio routing issues)
        try:
            # Suppress ALSA error messages during device scanning
            suppress_alsa_messages()
            
            self.audio = pyaudio.PyAudio()
            
            # If no device specified, try pipewire/pulseaudio first
            if device_index is None:
                # Find pipewire or default device
                for i in range(self.audio.get_device_count()):
                    info = self.audio.get_device_info_by_index(i)
                    name = info['name'].lower()
                    if 'pipewire' in name or 'pulse' in name or info['name'] == 'default':
                        device_index = i
                        print(f"[AUDIO] Auto-selected device {i}: {info['name']}")
                        break
            
            # Use blocking mode (write directly) - works better with PulseAudio
            self.stream = self.audio.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=sample_rate,
                output=True,
                output_device_index=device_index,
                frames_per_buffer=128  # Low latency (~2.6ms at 48kHz)
            )
            
            if device_index is not None:
                device_info = self.audio.get_device_info_by_index(device_index)
                print(f"[AUDIO] Using device {device_index}: {device_info['name']}")
            
            print(f"[AUDIO] Stream opened successfully: {sample_rate}Hz, {self.frequency}Hz tone, volume={self.volume}")
        except Exception as e:
            print(f"[AUDIO ERROR] Failed to open audio stream: {e}")
            raise
        
        # Start audio generation thread (blocking mode)
        self.running = True
        self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.audio_thread.start()
    
    def _audio_loop(self):
        """Audio generation thread (blocking mode)"""
        chunk_size = 128
        
        while self.running:
            # Generate audio chunk
            samples = np.zeros(chunk_size, dtype=np.float32)
            
            for i in range(chunk_size):
                # Update target envelope based on key state
                self.target_envelope = 1.0 if self.key_down else 0.0
                
                # Smooth envelope transition
                if self.key_down:
                    self.envelope = min(self.envelope + self.rise_rate, self.target_envelope)
                else:
                    self.envelope = max(self.envelope - self.fall_rate, self.target_envelope)
                
                # Generate sine wave
                if self.envelope > 0.0001:
                    # math.sin is ~20x faster than numpy scalar np.sin;
                    # the audio thread must outpace 128 samples / 2.67ms
                    raw_sample = math.sin(self.two_pi * self.phase) * self.envelope * self.volume
                    self.filter_state += self.filter_alpha * (raw_sample - self.filter_state)
                    samples[i] = self.filter_state
                    
                    self.phase += self.phase_increment
                    if self.phase >= 1.0:
                        self.phase -= 1.0
                else:
                    samples[i] = 0.0
                    self.filter_state = 0.0
            
            # Write to stream (blocking but fast)
            try:
                self.stream.write(samples.tobytes(), exception_on_underflow=False)
            except:
                pass  # Stream closed or error
    
    def set_key(self, key_down):
        """Set key state"""
        self.key_down = key_down
    
    def set_volume(self, volume):
        """Set sidetone volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
    
    def set_frequency(self, frequency):
        """Set sidetone frequency in Hz"""
        self.frequency = frequency
        self.phase_increment = frequency / self.sample_rate
    
    def close(self):
        """Cleanup"""
        if not AUDIO_AVAILABLE:
            return
        
        # Stop thread
        self.running = False
        self.key_down = False  # Ensure key is released
        
        # Wait briefly for thread to finish
        if hasattr(self, 'audio_thread') and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=0.2)
        
        # Close stream
        try:
            if hasattr(self, 'stream'):
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
        except Exception as e:
            pass  # Ignore cleanup errors
        
        # Terminate PyAudio
        try:
            if hasattr(self, 'audio'):
                self.audio.terminate()
        except Exception as e:
            pass  # Ignore cleanup errors