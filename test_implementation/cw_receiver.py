#!/usr/bin/env python3
"""
CW Receiver - Listen for CW keying events and generate sidetone
"""

import socket
import sys
import time
import threading
import queue
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


class JitterBuffer:
    """Buffer CW events to smooth out network jitter"""
    
    def __init__(self, buffer_ms=100):
        """
        Initialize jitter buffer with RELATIVE timing
        
        Args:
            buffer_ms: Buffer depth in milliseconds (recommended: 50-200ms)
        """
        self.buffer_ms = buffer_ms
        self.event_queue = queue.PriorityQueue()
        self.running = False
        self.callback = None
        self.start_time = None
        self.playback_time = 0  # Relative time in seconds
        self.last_arrival = None
        
    def add_event(self, key_down, duration_ms, arrival_time):
        """Add event to buffer using RELATIVE timing to preserve tempo"""
        
        # Reset if there's a long gap (>2 seconds) between transmissions
        if self.last_arrival and (arrival_time - self.last_arrival) > 2.0:
            self.start_time = None
            self.playback_time = 0
            # Clear old events from queue
            while not self.event_queue.empty():
                try:
                    self.event_queue.get_nowait()
                except queue.Empty:
                    break
        
        if self.start_time is None:
            self.start_time = arrival_time
            # First event plays after buffer delay
            self.playback_time = self.buffer_ms / 1000.0
        
        # Calculate playout time using RELATIVE timing
        # This preserves the original tempo regardless of network jitter
        playout_time = self.start_time + self.playback_time
        
        # ADAPTIVE: If event would be late, push entire timeline forward
        # Use minimal shift to avoid "dragging" effect
        now = time.time()
        if playout_time < now:
            # Event is late - shift timeline forward with minimal margin
            time_shift = now - playout_time + 0.01  # Just 10ms safety margin
            self.start_time += time_shift
            playout_time += time_shift
        
        # Add to priority queue (sorted by playout time)
        self.event_queue.put((playout_time, key_down, duration_ms))
        
        # Advance playback time by the event duration
        # This maintains the original timing relationship between events
        self.playback_time += duration_ms / 1000.0
        self.last_arrival = arrival_time
    
    def start(self, callback):
        """Start playout thread
        
        Args:
            callback: function(key_down, duration_ms) called at proper time
        """
        self.callback = callback
        self.running = True
        self.thread = threading.Thread(target=self._playout_loop, daemon=True)
        self.thread.start()
    
    def _playout_loop(self):
        """Play out events at the right time"""
        while self.running:
            try:
                # Get next event (non-blocking with timeout)
                playout_time, key_down, duration_ms = self.event_queue.get(timeout=0.01)
                
                # Wait until playout time
                now = time.time()
                delay = playout_time - now
                
                if delay > 0:
                    time.sleep(delay)
                elif delay < -0.5:
                    # Event is very late (>500ms), skip it
                    print(f"\n[WARNING] Dropped late event (delay: {-delay*1000:.0f}ms)")
                    continue
                
                # Play out event
                if self.callback:
                    self.callback(key_down, duration_ms)
                
            except queue.Empty:
                continue
    
    def drain_buffer(self, timeout=2.0):
        """Wait for buffer to empty (called on EOT)"""
        start = time.time()
        while not self.event_queue.empty() and (time.time() - start) < timeout:
            time.sleep(0.01)
    
    def stop(self):
        """Stop playout thread"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
    
    def get_stats(self):
        """Get buffer statistics"""
        return {
            'buffer_ms': self.buffer_ms,
            'queued_events': self.event_queue.qsize()
        }


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
    def __init__(self, port=UDP_PORT, enable_audio=True, jitter_buffer_ms=0):
        self.port = port
        self.jitter_buffer_ms = jitter_buffer_ms
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Increase UDP receive buffer to handle bursts
        # Default is often 128KB, we set to 1MB
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)
        except:
            pass  # Ignore if not supported
        
        self.socket.bind(('0.0.0.0', port))
        
        self.protocol = CWProtocol()
        self.stats = CWTimingStats()
        
        # Audio sidetone
        self.sidetone = None
        if enable_audio and AUDIO_AVAILABLE:
            self.sidetone = SidetoneGenerator(frequency=700)  # 700 Hz for RX
        
        # Jitter buffer (optional, for internet/WAN use)
        self.jitter_buffer = None
        if jitter_buffer_ms > 0:
            self.jitter_buffer = JitterBuffer(jitter_buffer_ms)
        
        self.last_sequence = -1
        self.packet_count = 0
        self.lost_packets = 0
        self.last_packet_time = 0
        
        print(f"CW Receiver listening on port {port}")
        if self.sidetone:
            print("Audio sidetone enabled (700 Hz)")
        else:
            print("Audio sidetone disabled (visual only)")
        if self.jitter_buffer:
            print(f"Jitter buffer enabled ({jitter_buffer_ms}ms) for WAN use")
        else:
            print("Jitter buffer disabled (LAN mode)")
        print("-" * 60)
    
    def _process_event(self, key_down, duration_ms, seq=0):
        """Process a CW event (called directly or from jitter buffer)"""
        # Update audio sidetone
        if self.sidetone:
            self.sidetone.set_key(key_down)
        
        # Record for statistics
        self.stats.add_event(key_down, duration_ms)
        
        # Visual feedback
        state_str = "█" * 40 if key_down else " " * 40
        status = "DOWN" if key_down else "UP  "
        
        jitter_info = ""
        if self.jitter_buffer:
            jitter_stats = self.jitter_buffer.get_stats()
            jitter_info = f" JBuf:{jitter_stats['queued_events']:2d}"
        
        print(f"\r[{state_str}] {status} {duration_ms:4d}ms | "
              f"Seq:{seq:3d} Pkts:{self.packet_count:4d} "
              f"Lost:{self.lost_packets:2d}{jitter_info}",
              end='', flush=True)
    
    def run(self):
        """Main receive loop"""
        # Start jitter buffer playout thread if enabled
        if self.jitter_buffer:
            self.jitter_buffer.start(lambda kd, dur: self._process_event(kd, dur))
        
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
                time_gap = receive_time - self.last_packet_time if self.last_packet_time > 0 else 0
                
                if self.last_sequence >= 0:
                    expected = (self.last_sequence + 1) % 256
                    if seq != expected:
                        lost = (seq - expected) % 256
                        
                        # Detect new transmission vs packet loss:
                        # 1. Large time gap (>2 seconds) = new transmission
                        # 2. Sequence goes backward (lost > 128) AND small jump = new transmission
                        # 3. Otherwise = real packet loss
                        
                        if time_gap > 2.0:
                            # Long silence = new transmission starting
                            print(f"\n[INFO] New transmission detected (silence: {time_gap:.1f}s)")
                        elif lost > 128 and seq < 10:
                            # Backward jump to low number = reset
                            print(f"\n[INFO] Sequence reset: expected {expected}, got {seq} (new transmission)")
                        else:
                            # Real packet loss during active transmission
                            self.lost_packets += lost
                            print(f"\n[WARNING] Lost {lost} packet(s) - expected {expected}, got {seq}")
                
                self.last_sequence = seq
                self.last_packet_time = receive_time
                
                # Check for End-of-Transmission
                if parsed.get('eot', False):
                    print(f"\n[EOT] Transmission complete, draining buffer...")
                    if self.jitter_buffer:
                        self.jitter_buffer.drain_buffer(timeout=2.0)
                    print("[EOT] Buffer drained")
                    continue
                
                # Process events
                for key_down, duration_ms in parsed['events']:
                    if self.jitter_buffer:
                        # Add to jitter buffer for delayed playout
                        self.jitter_buffer.add_event(key_down, duration_ms, receive_time)
                    else:
                        # Immediate playout (LAN mode)
                        self._process_event(key_down, duration_ms, seq)
                
        except KeyboardInterrupt:
            print("\n\nInterrupted")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup and show statistics"""
        if self.jitter_buffer:
            self.jitter_buffer.stop()
        
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
            
            if loss_rate > 10:
                print(f"\n⚠️  HIGH PACKET LOSS!")
                print("This will cause:")
                print("  - Incorrect dit/dah timing")
                print("  - Missing CW elements")
                print("  - Garbled morse code")
                print("\nSolutions:")
                print("  - Reduce WPM speed on sender")
                print("  - Increase UDP receive buffer")
                print("  - Check network congestion")
            elif loss_rate > 1:
                print(f"\n⚠️  Moderate packet loss - may affect high-speed CW")
            else:
                print(f"\n✓ Excellent - minimal packet loss!")
        
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
    import argparse
    
    parser = argparse.ArgumentParser(description='CW Protocol Receiver with Jitter Buffer')
    parser.add_argument('--port', type=int, default=UDP_PORT, help='UDP port (default: 7355)')
    parser.add_argument('--jitter-buffer', type=int, default=0, 
                       help='Jitter buffer size in ms (0=disabled, recommend 50-200 for WAN)')
    parser.add_argument('--no-audio', action='store_true', help='Disable audio sidetone')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW Protocol Receiver")
    print("=" * 60)
    
    if args.jitter_buffer > 0:
        print(f"\n💡 WAN Mode: Jitter buffer enabled ({args.jitter_buffer}ms)")
        print("   This smooths out internet latency variations")
        print("   Note: Adds {args.jitter_buffer}ms of intentional delay")
    else:
        print(f"\n💡 LAN Mode: Direct playout (no buffering)")
        print("   For internet use, try: --jitter-buffer 100")
    print()
    
    receiver = CWReceiver(args.port, enable_audio=not args.no_audio, 
                         jitter_buffer_ms=args.jitter_buffer)
    receiver.run()
