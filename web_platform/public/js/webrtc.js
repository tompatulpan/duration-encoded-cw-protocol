/**
 * WebRTC Client for CW Practice Platform
 * Handles peer-to-peer connections in mesh topology
 */

class WebRTCClient {
    constructor(signalingServerUrl) {
        this.signalingServerUrl = signalingServerUrl;
        this.ws = null;
        this.peers = new Map();  // peerId -> {connection, stream, callsign}
        this.localStream = null;
        this.roomId = null;
        this.myId = null;
        this.myCallsign = null;
        
        // ICE servers for NAT traversal
        this.iceServers = [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' }
        ];
        
        // Callbacks
        this.onPeerJoined = null;     // (peerId, callsign)
        this.onPeerLeft = null;       // (peerId)
        this.onStreamReceived = null; // (peerId, stream)
        this.onMessage = null;        // (peerId, message)
        this.onConnectionStateChange = null; // (state)
        
        // Statistics
        this.stats = {
            packetsSent: 0,
            packetsReceived: 0,
            bytesReceived: 0
        };
    }

    /**
     * Connect to signaling server and join room
     */
    async connect(roomId, callsign, localStream) {
        this.roomId = roomId;
        this.myCallsign = callsign;
        this.localStream = localStream;
        
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(this.signalingServerUrl);
                
                this.ws.onopen = () => {
                    console.log('Connected to signaling server');
                    // Join room
                    this._sendSignal({
                        type: 'join',
                        roomId: this.roomId,
                        callsign: this.myCallsign
                    });
                };
                
                this.ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    console.log('<<<< Received WebSocket message:', data.type, data);
                    this._handleSignalingMessage(data);
                };
                
                this.ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    reject(error);
                };
                
                this.ws.onclose = () => {
                    console.log('Disconnected from signaling server');
                    if (this.onConnectionStateChange) {
                        this.onConnectionStateChange('disconnected');
                    }
                };
                
                // Resolve after successful join
                const originalHandler = this.ws.onmessage;
                this.ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    if (data.type === 'joined') {
                        this.myId = data.peerId;
                        console.log('Joined room as', this.myId);
                        resolve(data.peerId);
                        this.ws.onmessage = originalHandler;
                    }
                    originalHandler(event);
                };
                
            } catch (error) {
                reject(error);
            }
        });
    }

    /**
     * Handle incoming signaling messages
     */
    async _handleSignalingMessage(message) {
        console.log('Signaling message:', message.type, message);
        
        switch (message.type) {
            case 'joined':
                // We successfully joined
                break;
                
            case 'peer-list':
                // Received list of existing peers - connect to each
                for (const peer of message.peers) {
                    if (peer.peerId !== this.myId) {
                        await this._createPeerConnection(peer.peerId, peer.callsign, true);
                    }
                }
                break;
                
            case 'peer-joined':
                // New peer joined - wait for their offer
                console.log('Peer joined:', message.callsign);
                if (this.onPeerJoined) {
                    this.onPeerJoined(message.peerId, message.callsign);
                }
                break;
                
            case 'peer-left':
                // Peer left - clean up connection
                this._removePeer(message.peerId);
                break;
                
            case 'offer':
                // Received offer from peer
                await this._handleOffer(message.from, message.callsign, message.offer);
                break;
                
            case 'answer':
                // Received answer to our offer
                await this._handleAnswer(message.from, message.answer);
                break;
                
            case 'ice-candidate':
                // Received ICE candidate
                await this._handleIceCandidate(message.from, message.candidate);
                break;
                
            case 'cw_event':
                // Received CW event from remote sender (Python client)
                if (this.onCWEvent) {
                    this.onCWEvent(message.peerId, message.callsign, message.event, message.duration);
                }
                break;
                
            case 'pong':
                // Heartbeat response
                break;
        }
    }

    /**
     * Create peer connection (initiator or responder)
     */
    async _createPeerConnection(peerId, callsign, isInitiator) {
        console.log(`Creating peer connection to ${callsign} (initiator: ${isInitiator})`);
        
        const pc = new RTCPeerConnection({ iceServers: this.iceServers });
        
        // Add local stream
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => {
                pc.addTrack(track, this.localStream);
            });
        }
        
        // Handle incoming stream
        pc.ontrack = (event) => {
            console.log('Received stream from', callsign);
            const stream = event.streams[0];
            const peerData = this.peers.get(peerId);
            if (peerData) {
                peerData.stream = stream;
            }
            if (this.onStreamReceived) {
                this.onStreamReceived(peerId, stream, callsign);
            }
        };
        
        // Handle ICE candidates
        pc.onicecandidate = (event) => {
            if (event.candidate) {
                this._sendSignal({
                    type: 'ice-candidate',
                    to: peerId,
                    candidate: event.candidate
                });
            }
        };
        
        // Handle connection state changes
        pc.onconnectionstatechange = () => {
            console.log(`Connection to ${callsign}:`, pc.connectionState);
            if (pc.connectionState === 'disconnected' || pc.connectionState === 'failed') {
                this._removePeer(peerId);
            }
        };
        
        // Store peer data
        this.peers.set(peerId, {
            connection: pc,
            callsign: callsign,
            stream: null
        });
        
        // If initiator, create and send offer
        if (isInitiator) {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            this._sendSignal({
                type: 'offer',
                to: peerId,
                offer: offer
            });
        }
        
        return pc;
    }

    /**
     * Handle incoming offer
     */
    async _handleOffer(peerId, callsign, offer) {
        let pc = this.peers.get(peerId)?.connection;
        
        // Create connection if it doesn't exist
        if (!pc) {
            pc = await this._createPeerConnection(peerId, callsign, false);
        }
        
        await pc.setRemoteDescription(new RTCSessionDescription(offer));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        
        this._sendSignal({
            type: 'answer',
            to: peerId,
            answer: answer
        });
    }

    /**
     * Handle incoming answer
     */
    async _handleAnswer(peerId, answer) {
        const peerData = this.peers.get(peerId);
        if (peerData) {
            await peerData.connection.setRemoteDescription(new RTCSessionDescription(answer));
        }
    }

    /**
     * Handle incoming ICE candidate
     */
    async _handleIceCandidate(peerId, candidate) {
        const peerData = this.peers.get(peerId);
        if (peerData) {
            await peerData.connection.addIceCandidate(new RTCIceCandidate(candidate));
        }
    }

    /**
     * Remove peer connection
     */
    _removePeer(peerId) {
        const peerData = this.peers.get(peerId);
        if (peerData) {
            peerData.connection.close();
            this.peers.delete(peerId);
            if (this.onPeerLeft) {
                this.onPeerLeft(peerId);
            }
        }
    }

    /**
     * Send signaling message
     */
    _sendSignal(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        }
    }

    /**
     * Send message (public method for CW events, etc.)
     */
    send(message) {
        this._sendSignal(message);
    }

    /**
     * Get list of connected peers
     */
    getPeers() {
        const peers = [];
        for (const [peerId, data] of this.peers.entries()) {
            peers.push({
                peerId: peerId,
                callsign: data.callsign,
                connectionState: data.connection.connectionState
            });
        }
        return peers;
    }

    /**
     * Get connection statistics
     */
    async getStats() {
        const stats = {
            peers: this.peers.size,
            connections: []
        };
        
        for (const [peerId, data] of this.peers.entries()) {
            const pcStats = await data.connection.getStats();
            let bytesReceived = 0;
            let packetsReceived = 0;
            
            pcStats.forEach(report => {
                if (report.type === 'inbound-rtp') {
                    bytesReceived += report.bytesReceived || 0;
                    packetsReceived += report.packetsReceived || 0;
                }
            });
            
            stats.connections.push({
                peerId: peerId,
                callsign: data.callsign,
                state: data.connection.connectionState,
                bytesReceived: bytesReceived,
                packetsReceived: packetsReceived
            });
        }
        
        return stats;
    }

    /**
     * Leave room and disconnect
     */
    disconnect() {
        // Close all peer connections
        for (const [peerId, data] of this.peers.entries()) {
            data.connection.close();
        }
        this.peers.clear();
        
        // Send leave message
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this._sendSignal({ type: 'leave' });
        }
        
        // Close WebSocket
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        // Stop local stream
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
            this.localStream = null;
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebRTCClient;
}
// Updated tis  2 dec 2025 08:09:03 CET
