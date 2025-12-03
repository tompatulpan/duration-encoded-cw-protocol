/**
 * Cloudflare Worker - WebRTC Signaling Server
 * Handles WebSocket connections for peer discovery and signaling
 */

/**
 * Durable Object for managing room state and WebSocket connections
 */
export class SignalingRoom {
    constructor(state, env) {
        this.state = state;
        this.env = env;
        this.peers = new Map(); // peerId -> {ws, callsign, isSender}
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
            isSender: false,
            ws: ws
        };
        
        ws.addEventListener('message', async msg => {
            try {
                const data = JSON.parse(msg.data);
                await this.handleMessage(ws, data, state);
            } catch (err) {
                console.error('Error handling message:', err);
            }
        });
        
        ws.addEventListener('close', async () => {
            if (state.peerId) {
                this.peers.delete(state.peerId);
                console.log(`${state.callsign} left, ${this.peers.size} remaining`);
                
                // Broadcast to remaining peers
                this.broadcast({
                    type: 'peer-left',
                    peerId: state.peerId,
                    callsign: state.callsign
                }, state.peerId);
            }
        });
    }

    async handleMessage(ws, message, state) {
        switch (message.type) {
            case 'join':
                state.peerId = this.generatePeerId();
                state.callsign = message.callsign;
                state.isSender = message.isSender || false;
                
                // Get existing WebRTC peers (not protocol senders)
                const existingPeers = Array.from(this.peers.values())
                    .filter(p => !p.isSender)
                    .map(p => ({
                        peerId: p.peerId,
                        callsign: p.callsign
                    }));
                
                // Add to peers
                this.peers.set(state.peerId, {
                    ws: ws,
                    peerId: state.peerId,
                    callsign: state.callsign,
                    isSender: state.isSender
                });
                
                console.log(`${state.callsign} joined as ${state.isSender ? 'sender' : 'listener'} (${this.peers.size} total)`);
                
                // Send confirmation
                this.send(ws, {
                    type: 'joined',
                    peerId: state.peerId,
                    roomId: message.roomId
                });
                
                // Send peer list if WebRTC peer
                if (!state.isSender && existingPeers.length > 0) {
                    this.send(ws, {
                        type: 'peer-list',
                        peers: existingPeers
                    });
                }
                
                // Notify others if WebRTC peer
                if (!state.isSender) {
                    this.broadcast({
                        type: 'peer-joined',
                        peerId: state.peerId,
                        callsign: state.callsign
                    }, state.peerId);
                }
                break;
                
            case 'offer':
            case 'answer':
            case 'ice-candidate':
                // Forward to specific peer
                const targetPeer = this.peers.get(message.to);
                if (targetPeer) {
                    this.send(targetPeer.ws, {
                        ...message,
                        from: state.peerId
                    });
                }
                break;
                
            case 'cw_event':
                console.log(`CW event from ${state.callsign}: ${message.event} ${message.duration}ms, broadcasting to ${this.peers.size - 1} other peers`);
                
                // Broadcast to OTHER peers only (exclude sender to avoid duplicate)
                // Sender already hears their own sidetone locally
                this.broadcast({
                    type: 'cw_event',
                    peerId: state.peerId,
                    callsign: state.callsign,
                    event: message.event,
                    duration: message.duration,
                    timestamp: message.timestamp
                }, state.peerId);  // Exclude sender
                break;
                
            case 'keepalive':
                // Respond to keepalive to prevent Cloudflare timeout
                // No need to broadcast, just acknowledge
                break;
                
            case 'ping':
                this.send(ws, { type: 'pong' });
                break;
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
        console.log(`Broadcast ${message.type} to ${sentCount} peers`);
    }

    send(ws, message) {
        try {
            ws.send(JSON.stringify(message));
        } catch (err) {
            console.error('Error sending message:', err);
        }
    }

    generatePeerId() {
        return Math.random().toString(36).substr(2, 9);
    }
}

export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);
        
        // Handle WebSocket upgrade for signaling
        if (url.pathname === '/ws') {
            // Extract room ID from query param or use 'default'
            const roomId = url.searchParams.get('room') || 'main';
            
            // Get Durable Object stub for this room
            const id = env.SIGNALING_ROOM.idFromName(roomId);
            const stub = env.SIGNALING_ROOM.get(id);
            
            // Forward request to Durable Object
            return stub.fetch(request);
        }
        
        // Handle API requests
        if (url.pathname === '/api/rooms') {
            return new Response(JSON.stringify({ rooms: [] }), {
                headers: { 'Content-Type': 'application/json' }
            });
        }
        
        // Serve static content (handled by Cloudflare Pages)
        return new Response('Not found', { status: 404 });
    }
};