/**
 * Audio handling for CW Practice Platform
 * - Web Audio API for sidetone generation
 * - Audio input detection and analysis
 * - Tone detection for CW decoding
 */

class AudioHandler {
    constructor() {
        this.audioContext = null;
        this.microphone = null;
        this.analyser = null;
        this.scriptProcessor = null;
        
        // Sidetone oscillator
        this.sidetoneOsc = null;
        this.sidetoneGain = null;
        this.sidetoneFreq = 600;
        this.sidetoneVolume = 0.5;  // Increased from 0.3 for better audibility
        
        // Monitor control
        this.monitorGain = null;
        
        // Tone detection
        this.toneDetector = null;
        this.onToneStart = null;  // Callback when tone detected
        this.onToneEnd = null;    // Callback when tone stops
        this.isToneActive = false;
        this.toneStartTime = null;
        this.toneEndTime = null;
        
        // Audio input status
        this.isInputActive = false;
        this.inputLevel = 0;
    }

    /**
     * Initialize Web Audio API (no microphone needed for remote CW playback)
     */
    async init() {
        try {
            // Create audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            
            // Setup sidetone generator for remote CW playback
            this._setupSidetone();
            
            console.log('Audio initialized (sidetone only, no microphone)');
            return true;
        } catch (error) {
            console.error('Failed to initialize audio:', error);
            return false;
        }
    }

    /**
     * Setup sidetone oscillator - just create gain node
     */
    _setupSidetone() {
        // Create gain node
        this.sidetoneGain = this.audioContext.createGain();
        this.sidetoneGain.gain.value = 0;  // Start muted
        this.sidetoneGain.connect(this.audioContext.destination);
        
        // Oscillator will be created on first use (after AudioContext is running)
        this.sidetoneOsc = null;
        
        console.log('Sidetone gain node created');
    }
    
    /**
     * Ensure oscillator is created and running
     */
    _ensureOscillator() {
        if (!this.sidetoneOsc && this.audioContext && this.audioContext.state === 'running') {
            this.sidetoneOsc = this.audioContext.createOscillator();
            this.sidetoneOsc.type = 'sine';
            this.sidetoneOsc.frequency.value = this.sidetoneFreq;
            this.sidetoneOsc.connect(this.sidetoneGain);
            this.sidetoneOsc.start();
            console.log('Sidetone oscillator created and started');
        }
    }

    /**
     * Set monitor (microphone playback) volume
     */
    setMonitorVolume(volume) {
        if (this.monitorGain) {
            this.monitorGain.gain.value = volume;
            console.log('Monitor volume set to:', volume);
        }
    }

    /**
     * Start sidetone - creates a fresh oscillator each time
     */
    startSidetone() {
        console.log('startSidetone called, context:', this.audioContext?.state);
        
        if (!this.audioContext || !this.sidetoneGain) {
            console.log('No audioContext or sidetoneGain, returning');
            return;
        }
        
        if (this.audioContext.state !== 'running') {
            console.log('AudioContext not running:', this.audioContext.state);
            return;
        }
        
        // Stop any previous oscillator immediately
        if (this.sidetoneOsc) {
            try {
                this.sidetoneOsc.stop();
                this.sidetoneOsc.disconnect();
            } catch (e) {
                // Ignore - oscillator already stopped
            }
            this.sidetoneOsc = null;
        }
        
        // Create a fresh oscillator for this tone
        this.sidetoneOsc = this.audioContext.createOscillator();
        this.sidetoneOsc.type = 'sine';
        this.sidetoneOsc.frequency.value = this.sidetoneFreq;
        
        // Set gain to target volume
        this.sidetoneGain.gain.value = this.sidetoneVolume;
        
        // Connect and start ASAP
        this.sidetoneOsc.connect(this.sidetoneGain);
        this.sidetoneOsc.start(0); // Start at earliest possible time
        
        console.log(`✓ Sidetone started: ${this.sidetoneFreq}Hz @ ${this.sidetoneVolume}, currentTime: ${this.audioContext.currentTime}`);
    }

    /**
     * Stop sidetone - stops oscillator immediately
     */
    stopSidetone() {
        console.log('stopSidetone called, oscillator exists:', !!this.sidetoneOsc);
        
        if (!this.sidetoneOsc || !this.audioContext) {
            console.log('⚠️ No oscillator to stop or no context');
            return;
        }
        
        try {
            // Stop NOW - no scheduling needed
            this.sidetoneOsc.stop();
            this.sidetoneOsc.disconnect();
            this.sidetoneOsc = null;
            console.log('✓ Sidetone stopped NOW');
        } catch (e) {
            console.warn('❌ Error stopping oscillator:', e);
        }
    }

    /**
     * Play a tone for a specific duration (for remote CW playback)
     * @param {number} duration - Duration in milliseconds
     */
    playSidetoneDuration(duration) {
        if (!this.audioContext || !this.sidetoneGain) {
            return;
        }
        
        if (this.audioContext.state !== 'running') {
            return;
        }
        
        if (duration <= 0) {
            return;
        }
        
        // Stop any existing oscillator
        if (this.sidetoneOsc) {
            try {
                this.sidetoneOsc.stop();
                this.sidetoneOsc.disconnect();
            } catch (e) {
                // Ignore
            }
            this.sidetoneOsc = null;
        }
        
        // Create oscillator
        const osc = this.audioContext.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = this.sidetoneFreq;
        
        // Set gain
        this.sidetoneGain.gain.value = this.sidetoneVolume;
        
        // Connect
        osc.connect(this.sidetoneGain);
        
        // Schedule start and stop
        const now = this.audioContext.currentTime;
        const stopTime = now + (duration / 1000);
        
        osc.start(now);
        osc.stop(stopTime);
        
        // Clean up after it's done
        osc.onended = () => {
            try {
                osc.disconnect();
            } catch (e) {
                // Already disconnected
            }
        };
    }

    /**
     * Set sidetone frequency
     */
    setSidetoneFrequency(freq) {
        this.sidetoneFreq = freq;
        if (this.sidetoneOsc) {
            this.sidetoneOsc.frequency.value = freq;
        }
    }

    /**
     * Set sidetone volume (0-1)
     */
    setSidetoneVolume(volume) {
        this.sidetoneVolume = volume;
        console.log('Sidetone volume set to:', volume);
        // Note: Actual gain is set in startSidetone() with fade-in
    }

    /**
     * Process audio buffer for tone detection
     */
    _processToneDetection(event) {
        const inputBuffer = event.inputBuffer.getChannelData(0);
        const bufferLength = inputBuffer.length;
        
        // Calculate RMS (Root Mean Square) for volume level
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += inputBuffer[i] * inputBuffer[i];
        }
        const rms = Math.sqrt(sum / bufferLength);
        this.inputLevel = rms;
        
        // Simple threshold-based tone detection
        const threshold = 0.02;  // Adjust based on testing
        const toneDetected = rms > threshold;
        
        // State change detection
        if (toneDetected && !this.isToneActive) {
            // Tone started
            this.isToneActive = true;
            this.toneStartTime = Date.now();
            console.log('Tone detected, RMS:', rms.toFixed(4));
            if (this.onToneStart) {
                this.onToneStart();
            }
        } else if (!toneDetected && this.isToneActive) {
            // Tone ended
            this.isToneActive = false;
            this.toneEndTime = Date.now();
            const duration = this.toneEndTime - this.toneStartTime;
            console.log('Tone ended, duration:', duration, 'ms');
            if (this.onToneEnd) {
                this.onToneEnd(duration);
            }
        }
    }

    /**
     * Get current input level (0-1)
     */
    getInputLevel() {
        return this.inputLevel;
    }

    /**
     * Test sidetone (play for 500ms)
     */
    testTone() {
        this.startSidetone();
        setTimeout(() => this.stopSidetone(), 500);
    }

    /**
     * Cleanup
     */
    cleanup() {
        if (this.scriptProcessor) {
            this.scriptProcessor.disconnect();
            this.scriptProcessor = null;
        }
        if (this.analyser) {
            this.analyser.disconnect();
            this.analyser = null;
        }
        if (this.microphone) {
            this.microphone.disconnect();
            this.microphone = null;
        }
        if (this.sidetoneOsc) {
            this.sidetoneOsc.stop();
            this.sidetoneOsc = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        this.isInputActive = false;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AudioHandler;
}
 
