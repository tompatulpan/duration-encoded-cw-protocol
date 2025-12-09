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
        self.last_event_end_time = None  # When previous event finishes
        self.last_arrival = None
        
        # Statistics tracking
        self.stats_delays = []  # Delay between playout time and arrival
        self.stats_shifts = 0
        self.stats_shift_after_gap = 0  # Shifts after >100ms arrival gap (manual keying)
        self.stats_max_queue = 0
        
        # State validation
        self.expected_key_state = None  # None = first event, True = DOWN, False = UP
        self.state_errors = 0
        self.suppress_state_errors = False  # Suppress errors during FEC recovery with gaps
        
        # Watchdog for stuck key-down detection
        self.last_key_down_time = None  # When key last went down
        self.max_key_down_duration = 3.0  # Force UP after 3 seconds (safety timeout)
        
        # Debug mode
        self.debug = False
        
    def add_event(self, key_down, duration_ms, arrival_time):
        """Add event to buffer using RELATIVE timing to preserve tempo"""
        
        # Validate state transition (DOWN/UP must alternate)
        if self.expected_key_state is not None and key_down == self.expected_key_state:
            self.state_errors += 1
            # Only print error if not suppressed (FEC gaps can cause state mismatches)
            if not self.suppress_state_errors:
                print(f"\n[ERROR] Invalid state: got {'DOWN' if key_down else 'UP'} twice in a row (error #{self.state_errors})")
            # Don't return - try to continue anyway
        self.expected_key_state = key_down  # Track last state seen
        
        # Reset if there's a long gap (>2 seconds) between transmissions
        if self.last_arrival and (arrival_time - self.last_arrival) > 2.0:
            self.last_event_end_time = None
            # Clear old events from queue
            while not self.event_queue.empty():
                try:
                    self.event_queue.get_nowait()
                except queue.Empty:
                    break
        
        # Calculate playout time using RELATIVE timing
        # Each event starts when the previous event ends (preserves tempo)
        now = time.time()
        
        # Track arrival gap for debug and statistics
        arrival_gap = 0
        if self.last_arrival:
            arrival_gap = arrival_time - self.last_arrival
        
        if self.debug and arrival_gap > 0:
            print(f"\n[DEBUG] Arrival gap: {arrival_gap*1000:.1f}ms, Duration: {duration_ms}ms, State: {'DOWN' if key_down else 'UP'}")
        
        if self.last_event_end_time is None:
            # First event: schedule buffer_ms from now
            playout_time = now + self.buffer_ms / 1000.0
            if self.debug:
                print(f"[DEBUG] First event: playout in {self.buffer_ms}ms")
        else:
            # Subsequent events: start when previous event finished
            # Trust the packet timing - it already encodes correct durations
            playout_time = self.last_event_end_time
            if self.debug:
                delay_to_playout = (playout_time - now) * 1000
                print(f"[DEBUG] Scheduled playout: {delay_to_playout:.1f}ms from now")
        
        # ADAPTIVE: If event would be late, shift it forward
        if playout_time < now:
            lateness = (now - playout_time) * 1000
            # Event is late - shift forward with minimal margin
            playout_time = now + 0.01
            self.stats_shifts += 1
            
            # Track if this shift was after a long arrival gap (manual keying pattern)
            if arrival_gap > 0.1:
                self.stats_shift_after_gap += 1
            
            if self.debug:
                print(f"[DEBUG] LATE EVENT! Shifted by {lateness:.1f}ms (gap: {arrival_gap*1000:.1f}ms)")
        
        # Track headroom AFTER adaptive shift (time from NOW until playout)
        time_until_playout = playout_time - now
        self.stats_delays.append(time_until_playout * 1000.0)
        
        # Add to priority queue (sorted by playout time)
        self.event_queue.put((playout_time, key_down, duration_ms))
        
        # Track max queue depth
        queue_size = self.event_queue.qsize()
        if queue_size > self.stats_max_queue:
            self.stats_max_queue = queue_size
        
        # Track when THIS event will end (for scheduling next event)
        self.last_event_end_time = playout_time + duration_ms / 1000.0
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
            # Check for stuck key-down state
            if self.last_key_down_time is not None:
                stuck_duration = time.time() - self.last_key_down_time
                if stuck_duration > self.max_key_down_duration:
                    print(f"\n[WARNING] Key stuck DOWN for {stuck_duration:.1f}s - forcing UP")
                    # Force key up to recover from stuck state
                    if self.callback:
                        self.callback(False, 10)  # Short UP event to reset
                    self.last_key_down_time = None
                    self.expected_key_state = False  # Reset to UP state
            
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
                
                # Track key-down time for watchdog
                if key_down:
                    self.last_key_down_time = time.time()
                else:
                    self.last_key_down_time = None
                
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
        
        # Note: We deliberately do NOT reset last_event_end_time here
        # This allows continuous operation without buffer delay resets
        # Only reset state validation to allow starting fresh
        self.expected_key_state = None
        self.last_key_down_time = None  # Clear watchdog
    
    def reset_state_tracking(self):
        """Reset state validation (useful when FEC blocks have gaps)"""
        self.expected_key_state = None
        self.last_key_down_time = None  # Clear watchdog
        if self.debug:
            print("\n[DEBUG] State tracking reset (FEC block with gaps)")
    
    def suppress_state_validation(self, suppress=True):
        """Suppress state error messages (during FEC recovery with gaps)"""
        self.suppress_state_errors = suppress
        if self.debug and suppress:
            print("\n[DEBUG] State validation errors suppressed (FEC gaps expected)")
    
    def stop(self):
        """Stop playout thread"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
    
    def get_stats(self):
        """Get buffer statistics"""
        stats = {
            'buffer_ms': self.buffer_ms,
            'queued_events': self.event_queue.qsize(),
            'timeline_shifts': self.stats_shifts,
            'timeline_shifts_after_gap': self.stats_shift_after_gap,
            'max_queue_depth': self.stats_max_queue
        }
        
        if self.stats_delays:
            # delays = time from packet arrival until scheduled playout
            # Positive = packet has headroom, negative = packet arrived late
            # Note: avg can exceed buffer_ms when events queue up (later arrivals wait longer)
            stats['delay_min'] = min(self.stats_delays)
            stats['delay_avg'] = sum(self.stats_delays) / len(self.stats_delays)
            stats['delay_max'] = max(self.stats_delays)
            stats['samples'] = len(self.stats_delays)
            # Buffer utilization based on minimum headroom (closest we came to underrun)
            stats['buffer_used'] = self.buffer_ms - stats['delay_min']
        
        return stats
    
    def reset_stats(self):
        """Reset statistics counters"""
        self.stats_delays = []
        self.stats_shifts = 0
        self.stats_shift_after_gap = 0
        self.stats_max_queue = 0


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


class CWReceiver:
    def __init__(self, port=UDP_PORT, enable_audio=True, jitter_buffer_ms=0, debug=False):
        self.port = port
        self.jitter_buffer_ms = jitter_buffer_ms
        self.debug = debug
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
            self.jitter_buffer.debug = debug
        
        self.last_sequence = -1
        self.packet_count = 0
        self.lost_packets = 0
        self.last_packet_time = 0
        self.stats_update_counter = 0
        self.last_stats_time = time.time()
        
        print(f"CW Receiver listening on port {port}")
        if self.sidetone:
            print("Audio sidetone enabled (700 Hz)")
        else:
            print("Audio sidetone disabled (visual only)")
        if self.jitter_buffer:
            print(f"Jitter buffer enabled ({jitter_buffer_ms}ms) for WAN use")
            print("Statistics will update every 10 packets")
        else:
            print("Jitter buffer disabled (LAN mode)")
        print("-" * 60)
    
    def _show_stats(self):
        """Display jitter buffer statistics"""
        if not self.jitter_buffer:
            return
        
        stats = self.jitter_buffer.get_stats()
        if 'delay_min' not in stats:
            return
        
        print("\n" + "=" * 60)
        print("NETWORK STATISTICS")
        print("=" * 60)
        print(f"Buffer size:      {stats['buffer_ms']}ms")
        print(f"Max delay seen:   {stats['buffer_used']:.1f}ms ({stats['buffer_used']/stats['buffer_ms']*100:.0f}% of buffer)")
        print(f"Min delay seen:   {stats['delay_min']:.1f}ms")
        # Note: avg delay can exceed buffer size when events queue up (later events wait longer)
        print(f"Avg delay:        {stats['delay_avg']:.1f}ms (arrival-to-playout)")
        print(f"Timeline shifts:  {stats['timeline_shifts']}")
        
        # Show shift breakdown for manual keying vs network jitter
        gap_shifts = stats['timeline_shifts_after_gap']
        network_shifts = stats['timeline_shifts'] - gap_shifts
        if gap_shifts > 0:
            print(f"  - After gaps:   {gap_shifts} (manual keying pauses)")
        if network_shifts > 0:
            print(f"  - Network:      {network_shifts} (actual jitter)")
        
        print(f"Max queue depth:  {stats['max_queue_depth']}")
        print(f"Current queue:    {stats['queued_events']}")
        print(f"Samples:          {stats['samples']}")
        
        # Smart recommendations based on actual buffer usage and jitter patterns
        usage_percent = (stats['buffer_used'] / stats['buffer_ms']) * 100
        network_jitter_rate = network_shifts / max(1, stats['samples'])
        avg_delay_percent = (stats['delay_avg'] / stats['buffer_ms']) * 100
        
        if network_jitter_rate > 0.2:
            # Frequent network-induced shifts (>20% of packets) = real jitter problem
            print(f"\n⚠️  RECOMMENDATION: Increase buffer to {stats['buffer_ms'] + 50}ms (high network jitter)")
        elif usage_percent >= 98 and avg_delay_percent > 50:
            # Hitting ceiling (98%+) AND high average delay (>50%) = sustained high jitter
            needed = stats['buffer_ms'] + 20
            print(f"\n⚠️  RECOMMENDATION: Increase buffer to {int(needed)}ms (sustained high delays)")
        elif usage_percent < 60 and gap_shifts == stats['timeline_shifts']:
            # Low usage and all shifts are from gaps = buffer oversized for manual keying
            suggested = max(20, int(stats['buffer_used'] * 1.3))
            print(f"\n✓ Buffer larger than needed - could reduce to ~{suggested}ms")
        else:
            # Buffer is adequate
            if avg_delay_percent < 30:
                # Very low average delay = buffer much larger than needed
                print(f"\n✓ Buffer size excellent (avg delay only {avg_delay_percent:.0f}% of buffer)")
            else:
                print(f"\n✓ Buffer size looks good!")
        
        print("=" * 60 + "\n")
    
    def _process_event(self, key_down, duration_ms, seq=0):
        """Process a CW event (called directly or from jitter buffer)"""
        # Record for statistics
        self.stats.add_event(key_down, duration_ms)
        
        # Debug timing
        if self.debug:
            state_name = "DOWN" if key_down else "UP  "
            print(f"\n[PLAY] {state_name} for {duration_ms}ms at {time.time():.3f}")
        
        # Update audio sidetone
        if self.sidetone:
            self.sidetone.set_key(key_down)
        
        # Periodically show statistics (every 10 packets)
        if self.jitter_buffer and self.packet_count % 10 == 0:
            self.stats_update_counter += 1
            if self.stats_update_counter >= 3:  # Every 30 packets
                self._show_stats()
                self.stats_update_counter = 0
        
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
                        # 2. Sequence goes backward (lost >= 100) = likely wrap-around or reset
                        # 3. Small gap with sequence jump at wrap boundary = wrap-around
                        # 4. Otherwise = real packet loss
                        
                        if time_gap > 2.0:
                            # Long silence = new transmission starting
                            print(f"\n[INFO] New transmission detected (silence: {time_gap:.1f}s)")
                        elif lost >= 100:
                            # Large backward jump = sequence wrap or reset, not real loss
                            # This catches wraps like 255→0 (lost=1 in mod256, but 255 backward)
                            # and also 128→0 (lost=128 in mod256, but is actually wrap)
                            if self.debug:
                                print(f"\n[DEBUG] Sequence wrap: {self.last_sequence}→{seq}")
                        else:
                            # Real packet loss during active transmission
                            self.lost_packets += lost
                            print(f"\n[WARNING] Lost {lost} packet(s) - expected {expected}, got {seq}")
                
                self.last_sequence = seq
                self.last_packet_time = receive_time
                
                # Check for End-of-Transmission
                if parsed.get('eot', False):
                    print(f"\n[EOT] Transmission complete, draining buffer...", flush=True)
                    if self.jitter_buffer:
                        self.jitter_buffer.drain_buffer(timeout=2.0)
                        print("[EOT] Buffer drained and reset", flush=True)
                    else:
                        print("[EOT] No buffer to drain", flush=True)
                    continue
                
                # Process events
                for key_down, duration_ms in parsed['events']:
                    # Debug: show what packet was actually received (enable with --debug-packets)
                    if hasattr(self, 'debug_packets') and self.debug_packets:
                        print(f"\n[RX] Seq:{seq} {'DOWN' if key_down else 'UP  '} {duration_ms:3d}ms", flush=True)
                    
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
        
        # Show state validation errors if any
        if self.jitter_buffer and self.jitter_buffer.state_errors > 0:
            print(f"\n⚠️  STATE ERRORS: {self.jitter_buffer.state_errors}")
            print("   Protocol violation - DOWN/UP events not alternating properly")
            print("   This may indicate sender bug or packet reordering\n")
        
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
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug output')
    parser.add_argument('--debug-packets', action='store_true', help='Show every received packet')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("CW Protocol Receiver")
    print("=" * 60)
    
    if args.jitter_buffer > 0:
        print(f"\n💡 WAN Mode: Jitter buffer enabled ({args.jitter_buffer}ms)")
        print("   This smooths out internet latency variations")
        print(f"   Note: Adds {args.jitter_buffer}ms of intentional delay")
    else:
        print(f"\n💡 LAN Mode: Direct playout (no buffering)")
        print("   For internet use, try: --jitter-buffer 100")
    print()
    
    if args.debug:
        print("🐛 DEBUG MODE ENABLED - Verbose timing output\n")
    
    receiver = CWReceiver(args.port, enable_audio=not args.no_audio, 
                         jitter_buffer_ms=args.jitter_buffer, debug=args.debug)
    receiver.debug_packets = args.debug_packets
    if args.debug_packets:
        print("📦 PACKET DEBUG ENABLED - Showing all received packets\n")
    receiver.run()
