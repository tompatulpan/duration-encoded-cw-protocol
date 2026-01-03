#!/usr/bin/env python3
"""
Jitter Buffer - Smooth out network jitter for CW events
"""

import time
import threading
import queue


class JitterBuffer:
    """Buffer CW events to smooth out network jitter"""
    
    # Maximum recommended buffer size
    MAX_BUFFER_MS = 1000
    
    def __init__(self, buffer_ms=100):
        """
        Initialize jitter buffer with RELATIVE timing
        
        Args:
            buffer_ms: Buffer depth in milliseconds (recommended: 50-200ms, max: 1000ms)
        """
        # Validate buffer size
        if buffer_ms > self.MAX_BUFFER_MS:
            print(f"[WARNING] Buffer size {buffer_ms}ms exceeds recommended maximum of {self.MAX_BUFFER_MS}ms")
            print(f"[WARNING] This will cause {buffer_ms}ms audio delay - consider using smaller buffer")
        
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
        
        # Adaptive word space detection
        self.word_space_base_threshold = 0.250  # 250ms base threshold (increased from 200ms for WiFi)
        self.recent_gaps = []  # Track recent inter-packet gaps for adaptive detection
        self.max_recent_gaps = 20  # Sample size for gap statistics
        
        # State validation
        self.expected_key_state = None  # None = first event, True = DOWN, False = UP
        self.state_errors = 0
        self.suppress_state_errors = False  # Suppress errors during FEC recovery with gaps
        
        # Watchdog for stuck key-down detection
        self.last_key_down_time = None  # When key last went down
        self.last_activity_time = None  # When last event was added (for stuck detection)
        # Stuck timeout adapts to buffer size (minimum 2s, or 2x buffer size)
        self.max_stuck_duration = max(2.0, (buffer_ms * 2) / 1000.0)
        
        # Debug mode
        self.debug = False
        
    def _update_gap_statistics(self, gap_ms):
        """Track recent gaps to distinguish network delays from intentional pauses"""
        self.recent_gaps.append(gap_ms)
        if len(self.recent_gaps) > self.max_recent_gaps:
            self.recent_gaps.pop(0)
    
    def _is_word_space(self, gap_ms):
        """
        Detect word spaces using adaptive threshold.
        
        Word space characteristics:
        - At 25 WPM: 336ms (7 × 48ms dit)
        - At 20 WPM: 420ms (7 × 60ms dit)
        - At 15 WPM: 560ms (7 × 80ms dit)
        
        Network delay characteristics:
        - LAN: <5ms
        - Good WiFi: 50-150ms
        - Poor WiFi: 150-250ms
        
        Strategy: Adapt based on observed gaps - word space is much larger than typical gaps
        """
        # Need enough samples to calculate median
        if len(self.recent_gaps) < 10:
            # Fallback: use simple threshold (only truly long gaps)
            # This avoids false positives during warmup period
            return gap_ms >= 300  # Conservative - only actual word spaces (336ms at 25 WPM)
        
        # Calculate median of ALL recent gaps (includes element, letter, and word spaces)
        sorted_gaps = sorted(self.recent_gaps)
        median_gap = sorted_gaps[len(sorted_gaps) // 2]
        
        # Word space should be significantly larger than typical gaps
        # At 25 WPM: word space (336ms) vs letter space (144ms) = 2.33x ratio
        # Use 4.0x median to account for letter space + network delay on WiFi
        # - LAN: median ~48ms → threshold ~192ms (above letter space 144ms, catches word spaces 336ms)
        # - WiFi: median ~100ms → threshold ~400ms (above letter+delay 250ms, catches word spaces 450ms)
        adaptive_threshold = median_gap * 4.0
        
        # Enforce absolute minimum of 225ms to prevent false positives on letter spaces
        # Letter space at slowest common speed (15 WPM): 3 × 80ms = 240ms
        # With high WiFi jitter: could be 240ms - 20ms (early) = 220ms
        # Letter space at 25 WPM: 144ms + worst WiFi delay 80ms = 224ms
        # Word space at fastest speed (30 WPM): 7 × 40ms = 280ms minimum
        # Safe threshold: 225ms catches word spaces (280ms+) but not letter spaces (220ms-)
        adaptive_threshold = max(225, adaptive_threshold)
        
        if self.debug and gap_ms >= adaptive_threshold:
            print(f"[DEBUG] Adaptive word space: gap={gap_ms:.1f}ms, threshold={adaptive_threshold:.1f}ms, median={median_gap:.1f}ms")
        
        return gap_ms >= adaptive_threshold
    
    def add_event(self, key_down, duration_ms, arrival_time):
        """Add event to buffer using RELATIVE timing to preserve tempo"""
        
        # Update activity time for watchdog
        self.last_activity_time = time.time()
        
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
            # Update gap statistics for adaptive word space detection
            self._update_gap_statistics(arrival_gap * 1000)  # Convert to ms
        
        if self.debug and arrival_gap > 0:
            print(f"\n[DEBUG] Arrival gap: {arrival_gap*1000:.1f}ms, Duration: {duration_ms}ms, State: {'DOWN' if key_down else 'UP'}")
            # Show adaptive detection details
            is_ws = self._is_word_space(arrival_gap * 1000)
            print(f"[DEBUG] _is_word_space({arrival_gap*1000:.1f}ms) = {is_ws}, samples={len(self.recent_gaps)}")
        
        # Detect word space gaps using adaptive detection
        # Reset timeline to prevent "late event" shifts
        if self.last_event_end_time is not None and arrival_gap > 0 and self._is_word_space(arrival_gap * 1000):
            if self.debug:
                print(f"[DEBUG] Word space detected ({arrival_gap*1000:.0f}ms gap) - resetting timeline to maintain buffer")
            # Reset timeline: schedule this event with full buffer headroom
            self.last_event_end_time = None
        
        if self.last_event_end_time is None:
            # First event OR post-word-space: schedule buffer_ms from now
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
    
    def add_event_ts(self, key_down, duration_ms, sender_event_time):
        """
        Add event with absolute timestamp (for timestamp-based protocols)
        
        Args:
            key_down: Key state
            duration_ms: Duration in milliseconds
            sender_event_time: Absolute time when sender generated this event (in receiver's clock)
        """
        arrival_time = time.time()
        now = arrival_time
        
        # Schedule playout: sender's event time + buffer headroom
        playout_time = sender_event_time + self.buffer_ms / 1000.0
        
        if self.debug:
            delay_to_playout = (playout_time - now) * 1000
            print(f"[DEBUG] TS-based scheduling: {delay_to_playout:.1f}ms from now")
        
        # ADAPTIVE: If event would be late, shift it forward
        if playout_time < now:
            lateness = (now - playout_time) * 1000
            playout_time = now + 0.01
            self.stats_shifts += 1
            
            if self.debug:
                print(f"[DEBUG] LATE EVENT! Shifted by {lateness:.1f}ms")
        
        # Track headroom
        time_until_playout = playout_time - now
        self.stats_delays.append(time_until_playout * 1000.0)
        
        # Add to queue
        self.event_queue.put((playout_time, key_down, duration_ms))
        
        # Track max queue depth
        queue_size = self.event_queue.qsize()
        if queue_size > self.stats_max_queue:
            self.stats_max_queue = queue_size
        
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
            # Check for stuck key-down state (no activity while key is down)
            if self.last_key_down_time is not None and self.last_activity_time is not None:
                time_since_activity = time.time() - self.last_activity_time
                if time_since_activity > self.max_stuck_duration:
                    print(f"\n[WARNING] Key stuck DOWN (no activity for {time_since_activity:.1f}s) - forcing UP")
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
        # Note: We also do NOT reset recent_gaps - network characteristics persist!
        # Only reset state validation to allow starting fresh
        self.expected_key_state = None
        self.last_key_down_time = None  # Clear watchdog
    
    def reset_connection(self, reason="connection reset"):
        """Full reset for new connection - clears all state including gap statistics"""
        # Clear timing state
        self.last_event_end_time = None
        self.last_arrival = None
        
        # Clear queue
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                break
        
        # Reset state validation
        self.expected_key_state = None
        self.last_key_down_time = None
        self.last_activity_time = None
        
        # Reset gap statistics (new connection may have different network characteristics)
        self.recent_gaps = []
        
        if self.debug:
            print(f"\n[DEBUG] Full buffer reset ({reason})")
    
    def reset_state_tracking(self, reason="FEC block with gaps"):
        """Reset state validation (useful when FEC blocks have gaps)"""
        self.expected_key_state = None
        self.last_key_down_time = None  # Clear watchdog
        self.last_activity_time = time.time()  # Reset activity timer
        if self.debug:
            print(f"\n[DEBUG] State tracking reset ({reason})")
    
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
