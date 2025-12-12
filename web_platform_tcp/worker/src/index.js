/**
 * CW Studio - Cloudflare Worker (WebSocket Relay)
 * 
 * Simple pass-through relay for CW events between browsers.
 * Uses hibernatable WebSockets to work around Cloudflare's I/O limitations.
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // Handle WebSocket upgrade
    if (request.headers.get('Upgrade') === 'websocket') {
      return handleWebSocket(request, env);
    }
    
    // Health check
    if (url.pathname === '/health') {
      return new Response('OK', { status: 200 });
    }
    
    return new Response('CW Studio WebSocket Relay', { 
      status: 200,
      headers: { 'Content-Type': 'text/plain' }
    });
  }
};

/**
 * Handle WebSocket connection
 * 
 * NOTE: Due to Cloudflare Workers limitations, we cannot store WebSocket
 * objects globally and access them from different request contexts.
 * 
 * Solution: Echo messages back with room info, let clients handle P2P logic,
 * OR use Durable Objects for proper stateful WebSocket management.
 * 
 * For simplicity, we'll implement a broadcast-on-receipt pattern.
 */
function handleWebSocket(request, env) {
  const webSocketPair = new WebSocketPair();
  const [client, server] = Object.values(webSocketPair);
  
  server.accept();
  
  // Connection state (per-connection)
  let roomId = null;
  let callsign = null;
  let peerId = crypto.randomUUID();
  
  console.log(`[Worker] New WebSocket connection: ${peerId}`);
  
  server.addEventListener('message', async (event) => {
    try {
      const data = JSON.parse(event.data);
      
      console.log(`[Worker] Received message from ${peerId}:`, data.type);
      
      switch (data.type) {
        case 'join':
          roomId = data.roomId;
          callsign = data.callsign;
          
          // Send confirmation to this client only
          server.send(JSON.stringify({
            type: 'joined',
            peerId: peerId,
            roomId: roomId,
            peers: [] // Cannot track peers without Durable Objects
          }));
          
          console.log(`[Worker] User ${callsign} (${peerId}) joined room ${roomId}`);
          break;
          
        case 'cw_event':
          // Echo back to sender (for now - proper relay needs Durable Objects)
          const event = {
            ...data,
            callsign: data.callsign || callsign,
            peerId: data.peerId || peerId,
            serverReceivedMs: Date.now()
          };
          
          // NOTE: This only echoes back to the sender
          // For multi-user, we need Durable Objects
          console.log(`[Worker] Echoing CW event from ${callsign}`);
          server.send(JSON.stringify(event));
          break;
          
        case 'leave':
          console.log(`[Worker] User ${peerId} leaving`);
          break;
          
        default:
          console.log('[Worker] Unknown message type:', data.type);
      }
    } catch (error) {
      console.error('[Worker] Message handling error:', error);
      server.send(JSON.stringify({
        type: 'error',
        message: error.message
      }));
    }
  });
  
  server.addEventListener('close', () => {
    console.log(`[Worker] WebSocket closed: ${peerId}`);
  });
  
  server.addEventListener('error', (error) => {
    console.error('[Worker] WebSocket error:', error);
  });
  
  return new Response(null, {
    status: 101,
    webSocket: client,
  });
}

/**
 * NOTE: The original multi-user broadcast implementation doesn't work with
 * Cloudflare Workers due to cross-request I/O limitations.
 * 
 * To implement proper multi-user rooms, you need to use Cloudflare Durable Objects.
 * 
 * For now, this is a single-user echo server for testing the protocol.
 * Each user only receives their own events back.
 * 
 * See DEPLOYMENT.md for instructions on implementing Durable Objects for multi-user support.
 */
