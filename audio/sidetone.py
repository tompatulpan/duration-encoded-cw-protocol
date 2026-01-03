#!/usr/bin/env python3
"""
Sidetone Generator - Audio feedback for CW keying
"""

import threading

# Audio support (optional)
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


class SidetoneGenerator:
    """Generate audio sidetone with improved signal quality"""
    
    def __init__(self, frequency=600, sample_rate=48000, device_index=None):
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.volume = 0.3
        
        if not AUDIO_AVAILABLE:
            return
        
        try:
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
        
        # Start audio generation thread
        self.running = True
        self.audio_thread = threading.Thread(target=self._audio_loop)
        self.audio_thread.daemon = True
        self.audio_thread.start()
    
    def _audio_loop(self):
        """Audio generation thread with optimized signal generation"""
        chunk_size = 128  # Match frames_per_buffer for consistency
        
        # Pre-calculate constants
        phase_increment = self.frequency / self.sample_rate
        rise_rate = 1.0 / (self.rise_time * self.sample_rate)
        fall_rate = 1.0 / (self.fall_time * self.sample_rate)
        two_pi = 2.0 * np.pi
        
        while self.running:
            # Generate audio chunk
            samples = np.zeros(chunk_size, dtype=np.float32)
            
            for i in range(chunk_size):
                # Update target envelope based on key state
                self.target_envelope = 1.0 if self.key_down else 0.0
                
                # Smooth envelope transition (exponential attack/release)
                if self.key_down:
                    # Attack (key down)
                    self.envelope = min(self.envelope + rise_rate, self.target_envelope)
                else:
                    # Release (key up)
                    self.envelope = max(self.envelope - fall_rate, self.target_envelope)
                
                # Generate sine wave only when envelope > 0 (CPU optimization)
                if self.envelope > 0.0001:
                    raw_sample = np.sin(two_pi * self.phase) * self.envelope * self.volume
                    
                    # Simple low-pass filter to smooth audio (reduces high-freq artifacts)
                    self.filter_state += self.filter_alpha * (raw_sample - self.filter_state)
                    samples[i] = self.filter_state
                    
                    # Advance phase
                    self.phase += phase_increment
                    if self.phase >= 1.0:
                        self.phase -= 1.0
                else:
                    samples[i] = 0.0
                    self.filter_state = 0.0  # Reset filter when silent
            
            # Output audio
            try:
                self.stream.write(samples.tobytes())
            except:
                pass
    
    def set_key(self, key_down):
        """Set key state"""
        self.key_down = key_down
    
    def set_volume(self, volume):
        """Set sidetone volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
    
    def set_frequency(self, frequency):
        """Set sidetone frequency in Hz"""
        self.frequency = frequency
    
    def close(self):
        """Cleanup"""
        if not AUDIO_AVAILABLE:
            return
        
        self.running = False
        if hasattr(self, 'audio_thread'):
            self.audio_thread.join(timeout=1.0)
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()
