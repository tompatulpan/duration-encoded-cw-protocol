/**
 * Room Controller - Main application logic for practice room
 * Ties together WebRTC, audio, and CW decoder
 */

class RoomController {
    constructor() {
        this.roomId = null;
        this.myCallsign = null;
        this.webrtc = null;
        this.audio = null;
        this.decoders = new Map();  // peerId -> MorseDecoder
        this.myDecoder = null;
        
        // UI state
        this.isMuted = false;
        this.isDeafened = false;
        this.sidetoneEnabled = true;  // Will be synced with checkbox state on init
        this.autoDecodeEnabled = true;
        this.showTimestamps = true;
        this.showCallsigns = true;
        
        // Audio elements for remote streams
        this.audioElements = new Map();  // peerId -> HTMLAudioElement
        
        // Silence tracking for decoder
        this.lastToneEnd = Date.now();
        this.silenceCheckInterval = null;
    }

    /**
     * Initialize and join room
     */
    async init() {
        // Get room parameters from URL
        const urlParams = new URLSearchParams(window.location.search);
        this.roomId = urlParams.get('room') || 'main';
        this.myCallsign = urlParams.get('callsign') || 'GUEST';
        
        // Update UI
        document.getElementById('roomName').textContent = this.roomId;
        document.getElementById('myCallsign').textContent = this.myCallsign;
        
        // Initialize audio handler
        this.audio = new AudioHandler();
        const audioInitialized = await this.audio.init();
        
        if (!audioInitialized) {
            this._showError('Failed to initialize audio. Please check microphone permissions.');
            return false;
        }
        
        this._updateStatus('audioInputStatus', '🟢 Active');
        
        // Setup audio callbacks for CW decoding
        this.audio.onToneStart = () => this._handleToneStart();
        this.audio.onToneEnd = (duration) => this._handleToneEnd(duration);
        
        // Initialize my decoder
        this.myDecoder = new MorseDecoder(20);
        
        // Initialize WebRTC
        const signalingUrl = this._getSignalingUrl();
        this.webrtc = new WebRTCClient(signalingUrl);
        
        // Setup WebRTC callbacks
        this.webrtc.onPeerJoined = (peerId, callsign) => this._handlePeerJoined(peerId, callsign);
        this.webrtc.onPeerLeft = (peerId) => this._handlePeerLeft(peerId);
        this.webrtc.onStreamReceived = (peerId, stream, callsign) => this._handleStreamReceived(peerId, stream, callsign);
        this.webrtc.onCWEvent = (peerId, callsign, event, duration) => this._handleRemoteCWEvent(peerId, callsign, event, duration);
        
        try {
            // Connect to room (no local stream needed for protocol-only mode)
            await this.webrtc.connect(this.roomId, this.myCallsign, null);
            
            this._updateStatus('signalingStatus', '🟢 Connected');
            this._updateStatus('webrtcStatus', '🟢 Connected');
            this._updateConnectionStatus('connected');
            
            // Setup UI event handlers
            this._setupEventHandlers();
            
            // Setup one-time click handler to resume AudioContext (browser autoplay policy)
            this._setupAudioContextResume();
            
            // Start silence checking for word spacing
            this._startSilenceChecking();
            
            return true;
        } catch (error) {
            console.error('Failed to join room:', error);
            this._showError(`Failed to join room: ${error.message}`);
            return false;
        }
    }

    /**
     * Get signaling server WebSocket URL
     */
    _getSignalingUrl() {
        // For development, use local or configured server
        // For production, use the deployed Cloudflare Worker
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            return 'ws://localhost:8787/ws';
        } else {
            return 'wss://cw-studio-signaling.data4-9de.workers.dev/ws';
        }
    }

    /**
     * Handle tone start (key down)
     */
    _handleToneStart() {
        console.log('_handleToneStart called, sidetoneEnabled:', this.sidetoneEnabled, 'isMuted:', this.isMuted);
        // Start sidetone only if enabled and not muted
        if (this.sidetoneEnabled && !this.isMuted) {
            this.audio.startSidetone();
        }
    }

    /**
     * Handle tone end (key up)
     */
    _handleToneEnd(duration) {
        // Stop sidetone
        this.audio.stopSidetone();
        
        // Add to decoder
        if (this.autoDecodeEnabled && this.myDecoder) {
            this.myDecoder.addElement(duration);
            this.lastToneEnd = Date.now();
        }
    }

    /**
     * Send practice CW text (simulated)
     */
    async _sendPracticeCW() {
        const practiceTexts = [
            'PARIS PARIS',
            'CQ CQ CQ DE SM0ONR SM0ONR K',
            'THE QUICK BROWN FOX',
            'VVV TEST TEST DE SM0ONR',
            '73 ES GUD DX'
        ];
        
        const text = practiceTexts[Math.floor(Math.random() * practiceTexts.length)];
        console.log('Sending practice CW:', text);
        
        const morseTable = {
            'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
            'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
            'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
            'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
            'Y': '-.--', 'Z': '--..',
            '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
            '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.'
        };
        
        const ditDuration = 48; // ms (25 WPM)
        const dahDuration = ditDuration * 3;
        const elementSpace = ditDuration;
        const charSpace = ditDuration * 3;
        const wordSpace = ditDuration * 7;
        
        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            
            if (char === ' ') {
                await new Promise(resolve => setTimeout(resolve, wordSpace));
                continue;
            }
            
            const pattern = morseTable[char];
            if (!pattern) continue;
            
            for (let j = 0; j < pattern.length; j++) {
                const element = pattern[j];
                const duration = element === '.' ? ditDuration : dahDuration;
                
                // Play sidetone locally
                this.audio.startSidetone();
                
                // Send tone_start event
                this.webrtc.send({
                    type: 'cw_event',
                    event: 'tone_start',
                    duration: 0
                });
                
                await new Promise(resolve => setTimeout(resolve, duration));
                
                // Stop sidetone
                this.audio.stopSidetone();
                
                // Send tone_end event
                this.webrtc.send({
                    type: 'cw_event',
                    event: 'tone_end',
                    duration: duration
                });
                
                // Wait between elements
                await new Promise(resolve => setTimeout(resolve, elementSpace));
            }
            
            // Wait between characters
            await new Promise(resolve => setTimeout(resolve, charSpace));
        }
        
        console.log('Practice CW complete');
    }

    /**
     * Handle CW event from remote sender (Python client)
     */
    async _handleRemoteCWEvent(peerId, callsign, event, duration) {
        // console.log('🔊 Remote CW:', callsign, event, duration, 'ms'); // Uncomment for debugging
        
        // Visual feedback
        document.title = event === 'tone_start' ? '▄ CW Studio' : 'CW Studio';
        
        // Get or create decoder for this sender
        if (!this.decoders.has(peerId)) {
            console.log('Creating new decoder for', callsign);
            this.decoders.set(peerId, {
                decoder: new MorseDecoder(20),
                lastToneEnd: 0
            });
            // Add this sender to operators list
            this._addOperatorToList(peerId, callsign);
            this._updateOperatorStatus(peerId, 'connected');
        }
        const decoderData = this.decoders.get(peerId);
        const decoder = decoderData.decoder;
        
        if (event === 'tone_start') {
            // Don't do anything on tone_start - wait for tone_end with duration
            // Show banner if AudioContext is still suspended
            if (this.audio.audioContext && this.audio.audioContext.state === 'suspended') {
                const banner = document.getElementById('audioActivationBanner');
                if (banner) {
                    banner.style.display = 'block';
                }
                console.warn('⚠️ AudioContext suspended - click anywhere on the page to enable audio');
            }
        } else if (event === 'tone_end') {
            // Play the tone NOW for its duration (events arrive after the real tone)
            if (this.sidetoneEnabled && duration > 0) {
                this.audio.playSidetoneDuration(duration);
            }
            
            // Decode the element
            if (this.autoDecodeEnabled && duration > 0) {
                decoder.addElement(duration);
                decoderData.lastToneEnd = Date.now();
                console.log('Added element to decoder, duration:', duration);
                
                // Check for character/word spacing after a brief delay
                setTimeout(() => {
                    const silenceDuration = Date.now() - decoderData.lastToneEnd;
                    const result = decoder.checkSpacing(silenceDuration);
                    if (result.character) {
                        console.log('Decoded character:', result.character);
                        this._appendDecodedText(callsign, result.character, result.type === 'word');
                        
                        // Update WPM estimate
                        const wpm = decoder.estimateWPM();
                        document.getElementById('wpmEstimate').textContent = `${wpm} WPM`;
                        console.log('Estimated WPM:', wpm);
                    }
                }, 200);
            }
        }
    }

    /**
     * Check for character/word spacing during silence
     */
    _checkSilence() {
        if (!this.myDecoder || !this.autoDecodeEnabled) return;
        
        const silenceDuration = Date.now() - this.lastToneEnd;
        const result = this.myDecoder.checkSpacing(silenceDuration);
        
        if (result.character) {
            this._appendDecodedText(this.myCallsign, result.character, result.type === 'word');
            
            // Update WPM estimate
            const wpm = this.myDecoder.estimateWPM();
            document.getElementById('wpmEstimate').textContent = `${wpm} WPM`;
        }
    }

    /**
     * Start periodic silence checking
     */
    _startSilenceChecking() {
        this.silenceCheckInterval = setInterval(() => {
            this._checkSilence();
        }, 100);  // Check every 100ms
    }

    /**
     * Handle new peer joining
     */
    _handlePeerJoined(peerId, callsign) {
        console.log(`Peer joined: ${callsign}`);
        
        // Create decoder for this peer
        this.decoders.set(peerId, new MorseDecoder(20));
        
        // Add to operators list
        this._addOperatorToList(peerId, callsign);
        
        // Show system message
        this._appendSystemMessage(`${callsign} joined the room`);
    }

    /**
     * Handle peer leaving
     */
    _handlePeerLeft(peerId) {
        const decoder = this.decoders.get(peerId);
        if (decoder) {
            this.decoders.delete(peerId);
        }
        
        // Remove audio element
        const audioEl = this.audioElements.get(peerId);
        if (audioEl) {
            audioEl.pause();
            audioEl.srcObject = null;
            this.audioElements.delete(peerId);
        }
        
        // Remove from operators list
        this._removeOperatorFromList(peerId);
        
        // Get callsign before removing
        const operatorEl = document.querySelector(`[data-peer-id="${peerId}"]`);
        const callsign = operatorEl ? operatorEl.dataset.callsign : 'Unknown';
        
        this._appendSystemMessage(`${callsign} left the room`);
    }

    /**
     * Handle received audio stream from peer
     */
    _handleStreamReceived(peerId, stream, callsign) {
        console.log(`Received stream from ${callsign}`);
        
        // Create audio element for playback
        const audio = new Audio();
        audio.srcObject = stream;
        audio.autoplay = true;
        audio.volume = this.isDeafened ? 0 : 0.8;
        
        this.audioElements.set(peerId, audio);
        
        // Update operator status
        this._updateOperatorStatus(peerId, 'connected');
    }

    /**
     * Add operator to list
     */
    _addOperatorToList(peerId, callsign) {
        const operatorsList = document.getElementById('operatorsList');
        
        const operatorEl = document.createElement('div');
        operatorEl.className = 'operator-item';
        operatorEl.dataset.peerId = peerId;
        operatorEl.dataset.callsign = callsign;
        operatorEl.innerHTML = `
            <span class="operator-callsign">${callsign}</span>
            <span class="operator-status status-connecting">●</span>
        `;
        
        operatorsList.appendChild(operatorEl);
        this._updateOperatorCount();
    }

    /**
     * Remove operator from list
     */
    _removeOperatorFromList(peerId) {
        const operatorEl = document.querySelector(`[data-peer-id="${peerId}"]`);
        if (operatorEl) {
            operatorEl.remove();
        }
        this._updateOperatorCount();
    }

    /**
     * Update operator status indicator
     */
    _updateOperatorStatus(peerId, status) {
        const operatorEl = document.querySelector(`[data-peer-id="${peerId}"]`);
        if (operatorEl) {
            const statusEl = operatorEl.querySelector('.operator-status');
            statusEl.className = `operator-status status-${status}`;
        }
    }

    /**
     * Update operator count
     */
    _updateOperatorCount() {
        const count = document.querySelectorAll('.operator-item').length;
        document.getElementById('operatorCount').textContent = count;
    }

    /**
     * Append decoded text to display
     */
    _appendDecodedText(callsign, text, isWordBoundary = false) {
        const decodedTextEl = document.getElementById('decodedText');
        
        // Remove welcome message if present
        const welcomeMsg = decodedTextEl.querySelector('.system-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }
        
        // Find or create line for this callsign
        let lineEl = decodedTextEl.querySelector(`[data-callsign="${callsign}"]`);
        
        if (!lineEl) {
            lineEl = document.createElement('div');
            lineEl.className = 'decoded-line';
            lineEl.dataset.callsign = callsign;
            
            if (this.showTimestamps) {
                const timestamp = new Date().toTimeString().split(' ')[0];
                lineEl.innerHTML = `<span class="timestamp">[${timestamp}]</span> `;
            }
            
            if (this.showCallsigns) {
                lineEl.innerHTML += `<span class="callsign-label">${callsign}:</span> `;
            }
            
            lineEl.innerHTML += `<span class="decoded-content"></span>`;
            decodedTextEl.appendChild(lineEl);
        }
        
        const contentEl = lineEl.querySelector('.decoded-content');
        contentEl.textContent += isWordBoundary ? ` ${text}` : text;
        
        // Auto-scroll to bottom
        decodedTextEl.scrollTop = decodedTextEl.scrollHeight;
    }

    /**
     * Append system message
     */
    _appendSystemMessage(message) {
        const decodedTextEl = document.getElementById('decodedText');
        
        const msgEl = document.createElement('p');
        msgEl.className = 'system-message';
        msgEl.textContent = message;
        
        decodedTextEl.appendChild(msgEl);
        decodedTextEl.scrollTop = decodedTextEl.scrollHeight;
    }

    /**
     * Update connection status
     */
    _updateConnectionStatus(status) {
        const statusEl = document.getElementById('connectionStatus');
        statusEl.className = `status-${status}`;
        statusEl.textContent = `● ${status.charAt(0).toUpperCase() + status.slice(1)}`;
    }

    /**
     * Update individual status indicator
     */
    _updateStatus(elementId, text) {
        document.getElementById(elementId).textContent = text;
    }

    /**
     * Show error message
     */
    _showError(message) {
        alert(message);  // TODO: Better error UI
    }

    /**
     * Setup one-time handler to resume AudioContext on first user interaction
     */
    _setupAudioContextResume() {
        const banner = document.getElementById('audioActivationBanner');
        
        const resumeAudio = async () => {
            if (this.audio.audioContext && this.audio.audioContext.state === 'suspended') {
                try {
                    await this.audio.audioContext.resume();
                    console.log('✅ AudioContext resumed after user interaction');
                    // Hide the banner
                    if (banner) {
                        banner.style.display = 'none';
                    }
                } catch (err) {
                    console.error('Failed to resume AudioContext:', err);
                }
            }
        };
        
        // Resume on any click, keypress, or touch
        const events = ['click', 'keydown', 'touchstart'];
        const handler = () => {
            resumeAudio();
            // Remove listeners after first interaction
            events.forEach(evt => document.removeEventListener(evt, handler));
        };
        events.forEach(evt => document.addEventListener(evt, handler, { once: true }));
    }

    /**
     * Setup UI event handlers
     */
    _setupEventHandlers() {
        // Leave button
        document.getElementById('leaveButton').addEventListener('click', () => {
            this.disconnect();
            window.location.href = 'index.html';
        });
        
        // Mute button
        document.getElementById('muteButton').addEventListener('click', () => {
            this.isMuted = !this.isMuted;
            const btn = document.getElementById('muteButton');
            if (this.isMuted) {
                btn.querySelector('.icon').textContent = '🎤';
                btn.querySelector('.label').textContent = 'Muted';
                btn.classList.add('active');
                // Stop sidetone when muting
                this.audio.stopSidetone();
            } else {
                btn.querySelector('.icon').textContent = '🎤';
                btn.querySelector('.label').textContent = 'Unmuted';
                btn.classList.remove('active');
            }
        });
        
        // Deafen button
        document.getElementById('deafenButton').addEventListener('click', () => {
            this.isDeafened = !this.isDeafened;
            const btn = document.getElementById('deafenButton');
            if (this.isDeafened) {
                btn.querySelector('.icon').textContent = '🔇';
                btn.querySelector('.label').textContent = 'Deafened';
                btn.classList.add('active');
                // Mute all remote audio
                this.audioElements.forEach(audio => audio.volume = 0);
            } else {
                btn.querySelector('.icon').textContent = '🔊';
                btn.querySelector('.label').textContent = 'Listening';
                btn.classList.remove('active');
                // Unmute remote audio
                this.audioElements.forEach(audio => audio.volume = 0.8);
            }
        });
        
        // Clear button
        document.getElementById('clearButton').addEventListener('click', () => {
            document.getElementById('decodedText').innerHTML = '';
        });
        
        // Sidetone toggle - sync initial state
        const sidetoneToggle = document.getElementById('sidetoneToggle');
        this.sidetoneEnabled = sidetoneToggle.checked;
        sidetoneToggle.addEventListener('change', (e) => {
            this.sidetoneEnabled = e.target.checked;
            // Stop sidetone if disabled
            if (!this.sidetoneEnabled) {
                this.audio.stopSidetone();
            }
        });
        
        // Sidetone frequency
        document.getElementById('sidetoneFreq').addEventListener('input', (e) => {
            const freq = parseInt(e.target.value);
            this.audio.setSidetoneFrequency(freq);
            document.getElementById('sidetoneFreqValue').textContent = `${freq} Hz`;
        });
        
        // Volume control (sidetone) - set initial value
        const volumeControl = document.getElementById('volumeControl');
        const initialVolume = parseInt(volumeControl.value) / 100;
        this.audio.setSidetoneVolume(initialVolume);
        
        document.getElementById('volumeControl').addEventListener('input', (e) => {
            const volume = parseInt(e.target.value) / 100;
            this.audio.setSidetoneVolume(volume);
            document.getElementById('volumeValue').textContent = `${e.target.value}%`;
        });
        
        // Practice CW button
        document.getElementById('practiceButton').addEventListener('click', () => {
            this._sendPracticeCW();
        });
        
        // Auto-decode checkbox
        document.getElementById('autoDecodeEnabled').addEventListener('change', (e) => {
            this.autoDecodeEnabled = e.target.checked;
        });
        
        // Timestamps checkbox
        document.getElementById('showTimestamps').addEventListener('change', (e) => {
            this.showTimestamps = e.target.checked;
        });
        
        // Callsigns checkbox
        document.getElementById('showCallsigns').addEventListener('change', (e) => {
            this.showCallsigns = e.target.checked;
        });
        
        // Font size selector
        document.getElementById('fontSize').addEventListener('change', (e) => {
            document.getElementById('decodedText').style.fontSize = `${e.target.value}px`;
        });
        
        // Test tone button
        document.getElementById('testToneButton').addEventListener('click', () => {
            this.audio.testTone();
        });
        
        // Help button
        document.getElementById('helpButton').addEventListener('click', () => {
            document.getElementById('helpModal').style.display = 'flex';
        });
        
        // Close help modal
        document.getElementById('closeHelp').addEventListener('click', () => {
            document.getElementById('helpModal').style.display = 'none';
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.disconnect();
                window.location.href = 'index.html';
            } else if (e.key === 'm' || e.key === 'M') {
                document.getElementById('muteButton').click();
            } else if (e.key === 'd' || e.key === 'D') {
                document.getElementById('deafenButton').click();
            } else if (e.key === 'c' || e.key === 'C') {
                document.getElementById('clearButton').click();
            } else if (e.key === '?') {
                document.getElementById('helpButton').click();
            }
        });
    }

    /**
     * Disconnect and cleanup
     */
    disconnect() {
        if (this.silenceCheckInterval) {
            clearInterval(this.silenceCheckInterval);
        }
        
        if (this.webrtc) {
            this.webrtc.disconnect();
        }
        
        if (this.audio) {
            this.audio.cleanup();
        }
        
        this.audioElements.forEach(audio => {
            audio.pause();
            audio.srcObject = null;
        });
        this.audioElements.clear();
    }
}

// Initialize on page load
let roomController;

document.addEventListener('DOMContentLoaded', async () => {
    roomController = new RoomController();
    const success = await roomController.init();
    
    if (!success) {
        // Show error and redirect after delay
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 3000);
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (roomController) {
        roomController.disconnect();
    }
});
 
 
