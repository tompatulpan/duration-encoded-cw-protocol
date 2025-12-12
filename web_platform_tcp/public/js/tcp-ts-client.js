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
    
    // Statistics
    this.stats = {
      eventsSent: 0,
      eventsReceived: 0,
      reconnects: 0
    };
    
    // Callbacks
    this.onConnected = null;
    this.onDisconnected = null;
    this.onPeerJoined = null;
    this.onPeerLeft = null;
    this.onCwEvent = null;
    this.onError = null;
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
        
        this.ws.onclose = () => {
          console.log('[TCP-TS] WebSocket closed');
          this.connected = false;
          if (this.onDisconnected) {
            this.onDisconnected();
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
        console.log('[TCP-TS] Received CW event:', data.callsign, 'key:', data.key_down, 'dur:', data.duration_ms);
        if (this.onCwEvent) {
          this.onCwEvent(data);
        }
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
   * Disconnect
   */
  disconnect() {
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
