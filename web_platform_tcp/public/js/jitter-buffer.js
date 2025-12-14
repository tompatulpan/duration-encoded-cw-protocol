/**
 * Jitter Buffer with Timestamp-based Scheduling
 * 
 * Schedules events at absolute times based on sender's timestamps.
 * Burst-resistant: WiFi/TCP bursts don't affect timing.
 */

class JitterBuffer {
  constructor(bufferMs = 150) {
    this.bufferMs = bufferMs;
    this.queue = [];
    this.running = false;
    this.senderTimelines = new Map(); // Track timeline per sender
    
    // Statistics
    this.stats = {
      eventsScheduled: 0,
      eventsPlayed: 0,
      maxQueueDepth: 0,
      lateEvents: 0
    };
    
    // Callback when event should play
    this.onPlayEvent = null;
  }
  
  /**
   * Add event to buffer
   */
  addEvent(event) {
    const now = performance.now();
    
    console.log('[JitterBuffer] Adding event:', event.callsign, 'key:', event.key_down, 'ts:', event.timestamp_ms);
    
    // Get or create sender timeline
    if (!this.senderTimelines.has(event.callsign)) {
      // First event from this sender - synchronize timeline
      // Calculate when sender's transmission started in our timeline
      // sender_start_time = now - timestamp_ms
      this.senderTimelines.set(event.callsign, {
        senderStartTime: now - event.timestamp_ms,  // When sender started (in our clock)
        firstSeen: now
      });
      console.log('[JitterBuffer] New sender timeline for:', event.callsign, 
                  'sender_start:', (now - event.timestamp_ms).toFixed(1), 'ms');
    }
    
    const timeline = this.senderTimelines.get(event.callsign);
    
    // Calculate absolute playout time using TCP-TS algorithm:
    // 1. sender_event_time = sender_start_time + timestamp_ms
    // 2. playout_time = sender_event_time + buffer_ms
    const senderEventTime = timeline.senderStartTime + event.timestamp_ms;
    const playoutTime = senderEventTime + this.bufferMs;
    
    // Debug: Log scheduling info
    const scheduleDelay = playoutTime - now;
    console.log('[JitterBuffer] Scheduling:', 
                'ts=' + event.timestamp_ms + 'ms',
                'playout_in=' + scheduleDelay.toFixed(1) + 'ms',
                'queue_depth=' + (this.queue.length + 1));
    
    // Add to queue
    this.queue.push({
      ...event,
      playoutTime,
      addedAt: now
    });
    
    // Sort by playout time (earliest first)
    this.queue.sort((a, b) => a.playoutTime - b.playoutTime);
    
    // Update statistics
    this.stats.eventsScheduled++;
    this.stats.maxQueueDepth = Math.max(this.stats.maxQueueDepth, this.queue.length);
    
    // Start processing if not running
    if (!this.running) {
      this.start();
    }
  }
  
  /**
   * Start processing queue
   */
  start() {
    if (this.running) return;
    
    this.running = true;
    this.processQueue();
  }
  
  /**
   * Process queue (check for events to play)
   */
  processQueue() {
    if (!this.running) return;
    
    const now = performance.now();
    
    // Play all events whose time has come
    while (this.queue.length > 0 && this.queue[0].playoutTime <= now) {
      const event = this.queue.shift();
      
      // Check if event is late
      const lateness = now - event.playoutTime;
      if (lateness > 10) {
        this.stats.lateEvents++;
        console.warn(`[JitterBuffer] Late event: ${lateness.toFixed(1)}ms`);
      }
      
      console.log('[JitterBuffer] Playing event:', event.callsign, 'key:', event.key_down);
      
      // Play event
      if (this.onPlayEvent) {
        this.onPlayEvent(event);
      }
      
      this.stats.eventsPlayed++;
    }
    
    // Schedule next check
    const nextCheckDelay = this.queue.length > 0
      ? Math.max(1, this.queue[0].playoutTime - now)
      : 100; // Check every 100ms if queue empty
    
    setTimeout(() => this.processQueue(), nextCheckDelay);
  }
  
  /**
   * Stop processing
   */
  stop() {
    this.running = false;
  }
  
  /**
   * Remove sender timeline (on disconnect)
   */
  removeSender(callsign) {
    console.log('[JitterBuffer] Removing sender timeline for:', callsign);
    this.senderTimelines.delete(callsign);
    
    // Remove any queued events from this sender
    const beforeCount = this.queue.length;
    this.queue = this.queue.filter(event => event.callsign !== callsign);
    const removed = beforeCount - this.queue.length;
    
    if (removed > 0) {
      console.log('[JitterBuffer] Removed', removed, 'queued events from', callsign);
    }
  }
  
  /**
   * Clear buffer
   */
  clear() {
    this.queue = [];
    this.senderTimelines.clear();
  }
  
  /**
   * Update buffer size
   */
  setBufferSize(bufferMs) {
    this.bufferMs = bufferMs;
  }
  
  /**
   * Get current queue depth
   */
  getQueueDepth() {
    return this.queue.length;
  }
  
  /**
   * Get statistics
   */
  getStats() {
    return {
      ...this.stats,
      queueDepth: this.queue.length,
      activeSenders: this.senderTimelines.size
    };
  }
}
