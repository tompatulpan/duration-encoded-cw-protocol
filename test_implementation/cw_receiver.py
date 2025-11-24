#!/usr/bin/env python3
"""
CW Receiver - Listen for CW keying events and generate sidetone
"""

import socket
import sys
import time
import threading
from cw_protocol import CWProtocol, CWTimingStats, UDP_PORT

# Audio support (optional)
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: pyaudio not available, audio sidetone disabled")
    print("Install with: pip3 install pyaudio")


class SidetoneGenerator:
    """Generate audio sidetone"""
    
    def __init__(self, frequency=600, sample_rate=48000):
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.volume = 0.3
        
        if not AUDIO_AVAILABLE:
            return
        
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=sample_rate,
            output=True,
            frames_per_buffer=256
        )
        
        self.phase = 0.0
        self.key_down = False
        self.envelope = 0.0
        
        # Envelope shaping to prevent clicks
        self.rise_time = 0.005  # 5ms
        self.fall_time = 0.005  # 5ms
        
        # Start audio generation thread
        self.running = True
        self.audio_thread = threading.Thread(target=self._audio_loop)
        self.audio_thread.daemon = True
        self.audio_thread.start()
    
    def _audio_loop(self):
        """Audio generation thread"""
        chunk_size = 256
        
        while self.running:
            # Generate audio chunk
            samples = np.zeros(chunk_size, dtype=np.float32)
            
            for i in range(chunk_size):
                # Update envelope
                target_envelope = 1.0 if self.key_down else 0.0
                envelope_rate = 1.0 / (self.rise_time * self.sample_rate) if self.key_down else \
                               1.0 / (self.fall_time * self.sample_rate)
                
                if self.envelope < target_envelope:
                    self.envelope = min(self.envelope + envelope_rate, target_envelope)
                elif self.envelope > target_envelope:
                    self.envelope = max(self.envelope - envelope_rate, target_envelope)
                
                # Generate sine wave
                samples[i] = self.volume * self.envelope * \
                            np.sin(2.0 * np.pi * self.phase)
                
                # Advance phase
                self.phase += self.frequency / self.sample_rate
                if self.phase >= 1.0:
                    self.phase -= 1.0
            
            # Output audio
            try:
                self.stream.write(samples.tobytes())
            except:
                pass
    
    def set_key(self, key_down):
        """Set key state"""
        self.key_down = key_down
    
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


class CWReceiver:
    def __init__(self, port=UDP_PORT, enable_audio=True):
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', port))
        
        self.protocol = CWProtocol()
        self.stats = CWTimingStats()
        
        # Audio sidetone
        self.sidetone = None
        if enable_audio and AUDIO_AVAILABLE:
            self.sidetone = SidetoneGenerator(frequency=700)  # 700 Hz for RX
        
        self.last_sequence = -1
        self.packet_count = 0
        self.lost_packets = 0
        
        print(f"CW Receiver listening on port {port}")
        if self.sidetone:
            print("Audio sidetone enabled (700 Hz)")
        else:
            print("Audio sidetone disabled (visual only)")
        print("-" * 60)
    
    def run(self):
        """Main receive loop"""
        try:
            while True:
                # Receive packet
                data, addr = self.socket.recvfrom(1024)
                receive_time = time.time()
                
                # Parse packet
                parsed = self.protocol.parse_packet(data)
                if not parsed:
                    continue
                
                self.packet_count += 1
                
                # Check for lost packets
                seq = parsed['sequence']
                if self.last_sequence >= 0:
                    expected = (self.last_sequence + 1) % 256
                    if seq != expected:
                        lost = (seq - expected) % 256
                        self.lost_packets += lost
                        print(f"\n[WARNING] Lost {lost} packet(s)")
                
                self.last_sequence = seq
                
                # Process events
                for key_down, duration_ms in parsed['events']:
                    # Update audio sidetone
                    if self.sidetone:
                        self.sidetone.set_key(key_down)
                    
                    # Record for statistics
                    self.stats.add_event(key_down, duration_ms)
                    
                    # Visual feedback
                    state_str = "█" * 40 if key_down else " " * 40
                    status = "DOWN" if key_down else "UP  "
                    
                    print(f"\r[{state_str}] {status} {duration_ms:4d}ms | "
                          f"Seq:{seq:3d} Pkts:{self.packet_count:4d} "
                          f"Lost:{self.lost_packets:2d}",
                          end='', flush=True)
                
        except KeyboardInterrupt:
            print("\n\nInterrupted")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup and show statistics"""
        if self.sidetone:
            self.sidetone.close()
        
        self.socket.close()
        
        print("\n" + "=" * 60)
        print("Session Statistics:")
        print("=" * 60)
        
        stats = self.stats.get_stats()
        print(f"Total packets received: {self.packet_count}")
        print(f"Packets lost: {self.lost_packets}")
        if self.packet_count > 0:
            loss_rate = (self.lost_packets / (self.packet_count + self.lost_packets)) * 100
            print(f"Packet loss rate: {loss_rate:.2f}%")
        
        print(f"\nTotal events: {stats.get('total_events', 0)}")
        print(f"Session duration: {stats.get('duration_sec', 0):.1f}s")
        
        if 'avg_dit_ms' in stats:
            print(f"\nTiming Analysis:")
            print(f"  Average dit: {stats['avg_dit_ms']:.1f}ms ({stats['dit_count']} dits)")
            if 'avg_dah_ms' in stats:
                print(f"  Average dah: {stats['avg_dah_ms']:.1f}ms ({stats['dah_count']} dahs)")
                print(f"  Dah/Dit ratio: {stats['dah_dit_ratio']:.2f} (ideal: 3.0)")
            if 'avg_space_ms' in stats:
                print(f"  Average space: {stats['avg_space_ms']:.1f}ms ({stats['space_count']} spaces)")
            print(f"  Estimated speed: {stats['wpm']:.1f} WPM")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = UDP_PORT
    
    receiver = CWReceiver(port)
    receiver.run()
