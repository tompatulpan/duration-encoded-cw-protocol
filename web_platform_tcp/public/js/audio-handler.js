/**
 * Audio Handler - Web Audio API
 * 
 * Manages sidetone generation with per-user oscillators.
 * Supports overlapping CW from multiple operators.
 */

class AudioHandler {
  constructor() {
    this.audioContext = null;
    this.masterGain = null;
    this.oscillators = new Map(); // callsign -> {osc, gain}
    this.enabled = true;
    this.volume = 0.3;
    this.baseFrequency = 700; // Hz
    
    this.initAudio();
  }
  
  /**
   * Initialize Web Audio API
   */
  initAudio() {
    try {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      
      // Master gain node
      this.masterGain = this.audioContext.createGain();
      this.masterGain.gain.value = this.volume;
      this.masterGain.connect(this.audioContext.destination);
      
      console.log('[Audio] Initialized, sample rate:', this.audioContext.sampleRate);
    } catch (error) {
      console.error('[Audio] Failed to initialize:', error);
    }
  }
  
  /**
   * Resume audio context (required after user interaction)
   */
  async resume() {
    if (this.audioContext && this.audioContext.state === 'suspended') {
      await this.audioContext.resume();
      console.log('[Audio] Context resumed');
    }
  }
  
  /**
   * Set key state for a user
   */
  setKey(callsign, keyDown, frequency = null) {
    if (!this.enabled || !this.audioContext) {
      console.log('[Audio] Skipping - disabled or no context');
      return;
    }
    
    console.log('[Audio] setKey:', callsign, 'keyDown:', keyDown);
    
    // Resume context if needed
    if (this.audioContext.state === 'suspended') {
      this.resume();
    }
    
    // Get or create oscillator for this user
    if (!this.oscillators.has(callsign)) {
      this.createOscillator(callsign, frequency);
    }
    
    const { gain } = this.oscillators.get(callsign);
    const now = this.audioContext.currentTime;
    
    // Envelope: 4ms attack/decay
    gain.gain.cancelScheduledValues(now);
    gain.gain.setValueAtTime(gain.gain.value, now);
    gain.gain.setTargetAtTime(keyDown ? 1.0 : 0.0, now, 0.004);
  }
  
  /**
   * Create oscillator for a user
   */
  createOscillator(callsign, frequency = null) {
    if (!this.audioContext) return;
    
    // Different frequency per user (easier to identify)
    const freq = frequency || this.baseFrequency + (this.hashCallsign(callsign) * 50);
    
    const osc = this.audioContext.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = freq;
    
    const gain = this.audioContext.createGain();
    gain.gain.value = 0.0; // Start silent
    
    osc.connect(gain);
    gain.connect(this.masterGain);
    
    osc.start();
    
    this.oscillators.set(callsign, { osc, gain, frequency: freq });
    
    console.log(`[Audio] Created oscillator for ${callsign} at ${freq}Hz`);
  }
  
  /**
   * Hash callsign to frequency offset (0-4)
   */
  hashCallsign(callsign) {
    let hash = 0;
    for (let i = 0; i < callsign.length; i++) {
      hash = ((hash << 5) - hash) + callsign.charCodeAt(i);
      hash = hash & hash;
    }
    return Math.abs(hash) % 5;
  }
  
  /**
   * Remove oscillator for a user
   */
  removeUser(callsign) {
    if (this.oscillators.has(callsign)) {
      const { osc, gain } = this.oscillators.get(callsign);
      
      // Fade out
      const now = this.audioContext.currentTime;
      gain.gain.setTargetAtTime(0.0, now, 0.01);
      
      // Stop and disconnect after fade
      setTimeout(() => {
        osc.stop();
        osc.disconnect();
        gain.disconnect();
        this.oscillators.delete(callsign);
      }, 100);
      
      console.log(`[Audio] Removed oscillator for ${callsign}`);
    }
  }
  
  /**
   * Set master volume
   */
  setVolume(volume) {
    this.volume = volume;
    if (this.masterGain) {
      this.masterGain.gain.value = volume;
    }
  }
  
  /**
   * Set base frequency
   */
  setFrequency(frequency) {
    this.baseFrequency = frequency;
    
    // Update existing oscillators
    this.oscillators.forEach(({ osc }, callsign) => {
      const freq = frequency + (this.hashCallsign(callsign) * 50);
      osc.frequency.value = freq;
    });
  }
  
  /**
   * Enable/disable audio
   */
  setEnabled(enabled) {
    this.enabled = enabled;
    
    if (!enabled) {
      // Mute all oscillators
      this.oscillators.forEach(({ gain }) => {
        const now = this.audioContext.currentTime;
        gain.gain.setTargetAtTime(0.0, now, 0.004);
      });
    }
  }
  
  /**
   * Clean up
   */
  destroy() {
    this.oscillators.forEach(({ osc, gain }) => {
      osc.stop();
      osc.disconnect();
      gain.disconnect();
    });
    this.oscillators.clear();
    
    if (this.audioContext) {
      this.audioContext.close();
    }
  }
}
