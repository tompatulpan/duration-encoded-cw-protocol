/**
 * CW Studio - Cloudflare Worker (WebSocket Relay)
 * 
 * Multi-user relay using Durable Objects for cross-connection broadcasting.
 */

/**
 * Durable Object for managing room state and WebSocket connections
 */
export class CWRoom {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.peers = new Map(); // peerId -> {ws, callsign}
  }

  async fetch(request) {
    const url = new URL(request.url);
    
    // Handle WebSocket upgrade
    if (request.headers.get('Upgrade') === 'websocket') {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      
      await this.handleSession(server);
      
      return new Response(null, {
        status: 101,
        webSocket: client,
      });
    }
    
    return new Response('Expected WebSocket', { status: 400 });
  }

  async handleSession(ws) {
    ws.accept();
    
    const state = { 
      peerId: null, 
      callsign: null,
      ws: ws
    };
    
    ws.addEventListener('message', async msg => {
      try {
        const data = JSON.parse(msg.data);
        await this.handleMessage(ws, data, state);
      } catch (err) {
        console.error('[CWRoom] Error handling message:', err);
      }
    });
    
    ws.addEventListener('close', async () => {
      if (state.peerId) {
        this.peers.delete(state.peerId);
        console.log(`[CWRoom] ${state.callsign} left, ${this.peers.size} remaining`);
        
        // Broadcast to remaining peers
        this.broadcast({
          type: 'peer_left',
          peerId: state.peerId,
          callsign: state.callsign
        }, state.peerId);
      }
    });
  }

  async handleMessage(ws, message, state) {
    switch (message.type) {
      case 'join':
        state.peerId = crypto.randomUUID();
        state.callsign = message.callsign;
        
        // Get existing peers
        const existingPeers = Array.from(this.peers.values())
          .map(p => ({
            peerId: p.peerId,
            callsign: p.callsign
          }));
        
        // Add to peers
        this.peers.set(state.peerId, {
          ws: ws,
          peerId: state.peerId,
          callsign: state.callsign
        });
        
        console.log(`[CWRoom] ${state.callsign} joined (${this.peers.size} total)`);
        
        // Send confirmation
        this.send(ws, {
          type: 'joined',
          peerId: state.peerId,
          roomId: message.roomId,
          peers: existingPeers
        });
        
        // Notify others
        this.broadcast({
          type: 'peer_joined',
          peerId: state.peerId,
          callsign: state.callsign
        }, state.peerId);
        break;
        
      case 'cw_event':
        console.log(`[CWRoom] CW event from ${state.callsign}: ${message.key_down ? 'DOWN' : 'UP'} dur=${message.duration_ms}ms ts=${message.timestamp_ms}ms, broadcasting to ${this.peers.size - 1} other peers`);
        
        // Broadcast to all other peers (not sender)
        this.broadcast({
          type: 'cw_event',
          callsign: state.callsign || message.callsign,
          peerId: state.peerId,
          key_down: message.key_down,
          duration_ms: message.duration_ms,
          timestamp_ms: message.timestamp_ms,
          sequence: message.sequence
        }, state.peerId);
        break;
        
      case 'keepalive':
        // Just acknowledge
        break;
        
      case 'leave':
        this.peers.delete(state.peerId);
        this.broadcast({
          type: 'peer_left',
          peerId: state.peerId,
          callsign: state.callsign
        }, state.peerId);
        break;
        
      default:
        console.log('[CWRoom] Unknown message type:', message.type);
    }
  }

  broadcast(message, exceptPeerId = null) {
    let sentCount = 0;
    for (const peer of this.peers.values()) {
      if (peer.peerId !== exceptPeerId) {
        this.send(peer.ws, message);
        sentCount++;
      }
    }
    if (sentCount > 0) {
      console.log(`[CWRoom] Broadcast ${message.type} to ${sentCount} peers`);
    }
  }

  send(ws, message) {
    try {
      ws.send(JSON.stringify(message));
    } catch (err) {
      console.error('[CWRoom] Send error:', err);
    }
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // Health check
    if (url.pathname === '/health') {
      return new Response('OK', { status: 200 });
    }
    
    // Handle WebSocket upgrade - route to Durable Object
    if (request.headers.get('Upgrade') === 'websocket') {
      // Extract room ID from query params (default: "main")
      const roomId = url.searchParams.get('room') || 'main';
      
      // Get Durable Object ID for this room
      const id = env.CW_ROOM.idFromName(roomId);
      const stub = env.CW_ROOM.get(id);
      
      // Forward request to Durable Object
      return stub.fetch(request);
    }
    
    return new Response('CW Studio WebSocket Relay (Durable Objects)', { 
      status: 200,
      headers: { 'Content-Type': 'text/plain' }
    });
  }
};
