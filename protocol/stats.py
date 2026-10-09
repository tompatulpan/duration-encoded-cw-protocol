#!/usr/bin/env python3
"""
CW Timing Statistics module
"""

import time


class CWTimingStats:
    """Track timing statistics for analysis"""
    
    def __init__(self):
        self.events = []
        self.start_time = time.time()
        
    def add_event(self, key_down, duration_ms, timestamp=None):
        """Record a CW event"""
        if timestamp is None:
            timestamp = time.time() - self.start_time
        
        self.events.append({
            'timestamp': timestamp,
            'key_down': key_down,
            'duration_ms': duration_ms
        })
    
    def get_stats(self):
        """Calculate statistics from recorded events"""
        if not self.events:
            return {
                'total_events': 0,
                'duration': 0,
                'avg_dit_ms': 0,
                'avg_dah_ms': 0
            }
        
        # Separate dit and dah durations
        dits = []
        dahs = []
        
        for event in self.events:
            if not event['key_down']:  # Only count key-down events
                continue
            
            duration = event['duration_ms']
            # Simple classification: < 100ms = dit, >= 100ms = dah
            if duration < 100:
                dits.append(duration)
            else:
                dahs.append(duration)
        
        return {
            'total_events': len(self.events),
            'duration': self.events[-1]['timestamp'],
            'avg_dit_ms': sum(dits) / len(dits) if dits else 0,
            'avg_dah_ms': sum(dahs) / len(dahs) if dahs else 0,
            'num_dits': len(dits),
            'num_dahs': len(dahs),
            'wpm': (1200 / (sum(dits) / len(dits))) if dits else 0
        }
    
    def print_stats(self):
        """Print formatted statistics"""
        stats = self.get_stats()
        
        print("\n=== CW Timing Statistics ===")
        print(f"Total events: {stats['total_events']}")
        print(f"Duration: {stats['duration']:.2f}s")
        
        if stats['num_dits'] > 0:
            print(f"Average dit: {stats['avg_dit_ms']:.1f}ms ({stats['num_dits']} dits)")
            estimated_wpm = 1200 / stats['avg_dit_ms']
            print(f"Estimated WPM: {estimated_wpm:.1f}")
        
        if stats['num_dahs'] > 0:
            print(f"Average dah: {stats['avg_dah_ms']:.1f}ms ({stats['num_dahs']} dahs)")
        
        print("===========================\n")
