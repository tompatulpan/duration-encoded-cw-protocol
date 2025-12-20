/**
 * TCP-TS WebSocket Client
 * 
 * Handles WebSocket communication with Cloudflare Worker relay.
 * Uses TCP timestamp protocol principles (timestamps for burst-resistance).
 */

class TCPTSClient {
  constructor(workerUrl) {
    this.workerUrl = workerUrl;
    this.ws = null;
    this.connected = false;
    this.roomId = null;
    this.callsign = null;
    this.peerId = null;
    this.sequence = 0;
    this.transmissionStart = null;
    this.keepaliveInterval = null;
    this.heartbeatTimeout = null;
    this.reconnectAttempt = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 1000; // Start with 1s
    this.intentionalClose = false;
    this.lastActivityTime = Date.now();
    
    // Statistics
    this.stats = {
      eventsSent: 0,
      eventsReceived: 0,
      reconnects: 0,
      connectionDrops: 0
    };
    
    // Callbacks
    this.onConnected = null;
    this.onDisconnected = null;
    this.onPeerJoined = null;
    this.onPeerLeft = null;
    this.onCwEvent = null;
    this.onError = null;
    this.onReconnecting = null;
  }
  
  /**
   * Connect to relay server and join room
   */
  connect(roomId, callsign) {
    this.roomId = roomId;
    this.callsign = callsign;
    this.transmissionStart = Date.now();
    
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.workerUrl);
        
        this.ws.onopen = () => {
          console.log('[TCP-TS] WebSocket connected');
          this.reconnectAttempt = 0; // Reset on successful connection
          this.lastActivityTime = Date.now();
          
          // Start heartbeat (sends ping, expects pong within timeout)
          this.startHeartbeat();
          
          // Join room
          this.send({
            type: 'join',
            roomId: this.roomId,
            callsign: this.callsign
          });
        };
        
        this.ws.onmessage = (event) => {
          this.handleMessage(JSON.parse(event.data));
        };
        
        this.ws.onerror = (error) => {
          console.error('[TCP-TS] WebSocket error:', error);
          if (this.onError) {
            this.onError(error);
          }
          reject(error);
        };
        
        this.ws.onclose = (event) => {
          console.log('[TCP-TS] WebSocket closed:', event.code, event.reason);
          this.connected = false;
          this.clearHeartbeat();
          
          if (this.onDisconnected) {
            this.onDisconnected();
          }
          
          // Auto-reconnect if not intentional close
          if (!this.intentionalClose && event.code !== 1000) {
            this.stats.connectionDrops++;
            this.scheduleReconnect();
          }
        };
        
        // Resolve when joined
        const originalOnConnected = this.onConnected;
        this.onConnected = (data) => {
          this.connected = true;
          this.peerId = data.peerId;
          if (originalOnConnected) {
            originalOnConnected(data);
          }
          resolve(data);
        };
        
      } catch (error) {
        reject(error);
      }
    });
  }
  
  /**
   * Handle incoming message
   */
  handleMessage(data) {
    this.lastActivityTime = Date.now();
    this.resetHeartbeatTimeout();
    
    switch (data.type) {
      case 'joined':
        console.log('[TCP-TS] Joined room:', data.roomId, 'Peer ID:', data.peerId);
        if (this.onConnected) {
          this.onConnected(data);
        }
        break;
        
      case 'peer_joined':
        console.log('[TCP-TS] Peer joined:', data.callsign, data.peerId);
        if (this.onPeerJoined) {
          this.onPeerJoined(data);
        }
        break;
        
      case 'peer_left':
        console.log('[TCP-TS] Peer left:', data.peerId);
        if (this.onPeerLeft) {
          this.onPeerLeft(data);
        }
        break;
        
      case 'cw_event':
        this.stats.eventsReceived++;
        if (window.DEBUG) console.log('[TCP-TS] Received CW event:', data.callsign, 'key:', data.key_down, 'dur:', data.duration_ms);
        if (this.onCwEvent) {
          this.onCwEvent(data);
        }
        break;
        
      case 'keepalive_ack':
        // Keepalive acknowledged by server (two-way communication maintained)
        console.log('[TCP-TS] Keepalive acknowledged');
        break;
        
      case 'error':
        console.error('[TCP-TS] Server error:', data.message);
        if (this.onError) {
          this.onError(new Error(data.message));
        }
        break;
        
      default:
        console.log('[TCP-TS] Unknown message type:', data.type);
    }
  }
  
  /**
   * Send CW event (TCP-TS style with timestamp)
   */
  sendCwEvent(keyDown, durationMs) {
    if (!this.connected) {
      console.warn('[TCP-TS] Not connected, cannot send event');
      return false;
    }
    
    // Calculate timestamp (milliseconds since transmission start)
    const timestampMs = Date.now() - this.transmissionStart;
    
    // Create event packet (TCP-TS format)
    const event = {
      type: 'cw_event',
      callsign: this.callsign,
      key_down: keyDown,
      duration_ms: Math.round(durationMs),
      timestamp_ms: timestampMs,
      sequence: this.sequence++
    };
    
    this.send(event);
    this.stats.eventsSent++;
    
    return true;
  }
  
  /**
   * Send generic message
   */
  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('[TCP-TS] WebSocket not ready, cannot send message');
    }
  }
  
  /**
   * Start heartbeat monitoring
   */
  startHeartbeat() {
    // Send ping every 30s (well below Cloudflare's 100s idle timeout)
    this.keepaliveInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({
          type: 'keepalive',
          timestamp: Date.now()
        });
        
        // Set timeout to detect dead connection
        this.heartbeatTimeout = setTimeout(() => {
          console.warn('[TCP-TS] Heartbeat timeout - connection appears dead');
          this.stats.connectionDrops++;
          if (this.ws) {
            this.ws.close();
          }
        }, 10000); // 10s timeout for response
        
        if (window.DEBUG) console.log('[TCP-TS] Heartbeat ping sent');
      }
    }, 30000); // 30 seconds
  }
  
  /**
   * Reset heartbeat timeout (called on any message received)
   */
  resetHeartbeatTimeout() {
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }
  
  /**
   * Clear heartbeat timers
   */
  clearHeartbeat() {
    if (this.keepaliveInterval) {
      clearInterval(this.keepaliveInterval);
      this.keepaliveInterval = null;
    }
    this.resetHeartbeatTimeout();
  }
  
  /**
   * Schedule reconnection attempt
   */
  scheduleReconnect() {
    if (this.reconnectAttempt >= this.maxReconnectAttempts) {
      console.error('[TCP-TS] Max reconnect attempts reached');
      if (this.onError) {
        this.onError(new Error('Failed to reconnect after ' + this.maxReconnectAttempts + ' attempts'));
      }
      return;
    }
    
    this.reconnectAttempt++;
    const delay = Math.min(this.reconnectDelay * this.reconnectAttempt, 30000);
    
    console.log(`[TCP-TS] Reconnecting in ${delay/1000}s (attempt ${this.reconnectAttempt}/${this.maxReconnectAttempts})`);
    
    if (this.onReconnecting) {
      this.onReconnecting({ attempt: this.reconnectAttempt, delay: delay });
    }
    
    setTimeout(() => {
      console.log('[TCP-TS] Attempting to reconnect...');
      this.stats.reconnects++;
      this.connect(this.roomId, this.callsign)
        .then(() => {
          console.log('[TCP-TS] ✓ Reconnected successfully');
        })
        .catch((err) => {
          console.error('[TCP-TS] Reconnection failed:', err);
          // Will trigger onclose handler which schedules next attempt
        });
    }, delay);
  }
  
  /**
   * Disconnect
   */
  disconnect() {
    this.intentionalClose = true;
    this.intentionalClose = true;
    
    // Clear all timers
    this.clearHeartbeat();
    
    if (this.ws) {
      this.send({ type: 'leave' });
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }
  
  /**
   * Get statistics
   */
  getStats() {
    return { ...this.stats };
  }
}
