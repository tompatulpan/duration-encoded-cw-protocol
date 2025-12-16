/**
 * CW Decoder
 * 
 * Decodes Morse code events to text with adaptive timing.
 */

class CWDecoder {
  constructor() {
    // Timing thresholds (in multiples of dit duration)
    // These values are tuned to reliably detect CW spacing with margin for timing variance
    this.TIMING_CONFIG = {
      ditDahThreshold: 2.0,      // Threshold between dit and dah
      letterSpaceThreshold: 2.5, // Letter space detection (standard = 3× dit)
      wordSpaceThreshold: 6.9,   // Word space detection (standard = 7× dit)
      avgDitSmoothFactor: 0.9    // Exponential moving average factor (0.9 = 90% old, 10% new)
    };
    
    // Morse code table
    this.morseTable = {
      '.-': 'A',    '-...': 'B',  '-.-.': 'C',  '-..': 'D',
      '.': 'E',     '..-.': 'F',  '--.': 'G',   '....': 'H',
      '..': 'I',    '.---': 'J',  '-.-': 'K',   '.-..': 'L',
      '--': 'M',    '-.': 'N',    '---': 'O',   '.--.': 'P',
      '--.-': 'Q',  '.-.': 'R',   '...': 'S',   '-': 'T',
      '..-': 'U',   '...-': 'V',  '.--': 'W',   '-..-': 'X',
      '-.--': 'Y',  '--..': 'Z',
      '-----': '0', '.----': '1', '..---': '2', '...--': '3',
      '....-': '4', '.....': '5', '-....': '6', '--...': '7',
      '---..': '8', '----.': '9',
      '.-.-.-': '.', '--..--': ',', '..--..': '?', '-..-.': '/',
      '-...-': '=', '-....-': '-', '.--.-.': '@',
      // Swedish letters
      '.--.-': 'Å', '.-.-': 'Ä',  '---.': 'Ö',
      // Prosigns (sent as single character, no space between elements)
      '.-.-.': '<AR>',  // End of message (dit-dah-dit-dah-dit) - also decodes as +
      '...-.-': '<SK>'  // End of contact (dit-dit-dit-dah-dit-dah)
    };
    
    // Per-user decoder state
    this.users = new Map();
    
    // Callback for decoded text
    this.onDecodedChar = null;
    this.onDecodedWord = null;
  }
  
  /**
   * Process CW event
   * 
   * CORRECTED PROTOCOL INTERPRETATION:
   * - key_down: NEW state (what we just transitioned TO)
   * - duration_ms: Duration of PREVIOUS state (before this transition)
   * 
   * Example for dit (48ms):
   *   key_down=false, duration_ms=48 → "was DOWN for 48ms, now UP" (element completed)
   * 
   * Example for word space (336ms):
   *   key_down=true, duration_ms=336 → "was UP for 336ms, now DOWN" (word space detected)
   */
  processEvent(event) {
    const { callsign, key_down, duration_ms, timestamp_ms } = event;
    
    console.log('[Decoder] Processing event:', callsign, 
                'key:', key_down ? 'DOWN' : 'UP', 
                'dur:', duration_ms + 'ms', 
                'ts:', timestamp_ms + 'ms');
    
    // Get or create user state
    if (!this.users.has(callsign)) {
      this.users.set(callsign, {
        buffer: [],
        avgDit: 50, // Initial estimate (24 WPM middle ground)
        wpm: 20,
        lastElementDuration: 0,
        elementCount: 0,
        flushTimer: null,
        consecutiveElementSpaces: 0,
        isManualKeying: false
      });
      console.log('[Decoder] New user:', callsign);
    }
    
    const user = this.users.get(callsign);
    
    // Clear any pending flush timer
    if (user.flushTimer) {
      clearTimeout(user.flushTimer);
      user.flushTimer = null;
    }
    
    // ===== CORRECTED PROTOCOL INTERPRETATION =====
    // duration_ms = how long key was in PREVIOUS state
    // key_down = NEW state after transition
    
    if (key_down) {
      // Transition TO DOWN
      // duration_ms = how long we were UP (spacing)
      const spaceDuration = duration_ms;
      
      console.log('[Decoder]', callsign, '→ DOWN transition, was UP for:', spaceDuration + 'ms');
      
      // Check for word/letter space BEFORE processing new element
      const letterSpaceThreshold = user.avgDit * this.TIMING_CONFIG.letterSpaceThreshold;
      const wordSpaceThreshold = user.avgDit * this.TIMING_CONFIG.wordSpaceThreshold;
      const elementSpaceThreshold = user.avgDit * 1.5; // ~1 dit
      
      // DIAGNOSTIC: Log threshold calculations
      console.log('[Decoder] DIAGNOSTIC:', callsign, 
                  'spaceDuration=' + spaceDuration + 'ms',
                  'avgDit=' + user.avgDit.toFixed(1) + 'ms',
                  'letterThreshold=' + letterSpaceThreshold.toFixed(1) + 'ms',
                  'wordThreshold=' + wordSpaceThreshold.toFixed(1) + 'ms',
                  'buffer=' + user.buffer.join(''));
      
      if (spaceDuration > wordSpaceThreshold) {
        console.log('[Decoder]', callsign, '*** WORD SPACE ***', spaceDuration + 'ms', 
                    '(threshold:', wordSpaceThreshold.toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
        user.isManualKeying = false;
        if (this.onWordSpace) {
          this.onWordSpace(callsign);
        }
      } else if (spaceDuration > letterSpaceThreshold) {
        console.log('[Decoder]', callsign, '*** LETTER SPACE ***', spaceDuration + 'ms',
                    '(threshold:', letterSpaceThreshold.toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
        user.isManualKeying = false;
      } else if (spaceDuration > elementSpaceThreshold) {
        // Element space - detect manual keying pattern
        user.consecutiveElementSpaces++;
        if (user.consecutiveElementSpaces >= 3 && !user.isManualKeying) {
          user.isManualKeying = true;
          console.log('[Decoder]', callsign, 'Manual paddle keying detected');
        }
      }
      
    } else {
      // Transition TO UP
      // duration_ms = how long we were DOWN (element duration)
      const elementDuration = duration_ms;
      
      console.log('[Decoder]', callsign, '→ UP transition, was DOWN for:', elementDuration + 'ms');
      
      // Classify as dit or dah
      const threshold = user.avgDit * this.TIMING_CONFIG.ditDahThreshold;
      const isDit = elementDuration < threshold;
      
      user.buffer.push(isDit ? '.' : '-');
      
      // Update timing estimates with adaptive smoothing
      const ditEquivalent = isDit ? elementDuration : elementDuration / 3;
      
      // Calculate speed change percentage
      const speedChange = Math.abs(ditEquivalent - user.avgDit) / user.avgDit;
      
      // Use faster adaptation if:
      // - Just starting (< 10 elements)
      // - Significant speed change detected (>20%)
      let smoothFactor;
      if (user.elementCount < 10) {
        smoothFactor = 0.7; // Fast initial adaptation
      } else if (speedChange > 0.2) {
        smoothFactor = 0.8; // Faster adaptation for speed changes
      } else {
        smoothFactor = this.TIMING_CONFIG.avgDitSmoothFactor; // Normal (0.9)
      }
      
      user.avgDit = user.avgDit * smoothFactor + ditEquivalent * (1 - smoothFactor);
      user.wpm = Math.round(1200 / user.avgDit);
      user.elementCount++;
      
      user.lastElementDuration = elementDuration;
      
      // Reset manual keying counter on actual elements
      user.consecutiveElementSpaces = 0;
      
      console.log('[Decoder]', callsign, 'Element:', isDit ? 'dit' : 'dah', 
                  elementDuration + 'ms', 'buffer:', user.buffer.join(''), 
                  'wpm:', user.wpm, 'avgDit:', user.avgDit.toFixed(1) + 'ms',
                  user.isManualKeying ? '(manual)' : '(auto)');
      
      // Set timeout for end-of-transmission
      const letterSpaceThreshold = user.avgDit * this.TIMING_CONFIG.letterSpaceThreshold;
      const timeoutMs = user.isManualKeying 
        ? letterSpaceThreshold * 1.5
        : letterSpaceThreshold * 2;
      
      user.flushTimer = setTimeout(() => {
        console.log('[Decoder]', callsign, 'Flush timeout triggered');
        this.flushCharacter(callsign, user);
        user.isManualKeying = false;
      }, timeoutMs);
    }
  }
  
  /**
   * Flush current character buffer
   */
  flushCharacter(callsign, user) {
    console.log('[Decoder] flushCharacter called for:', callsign, 'buffer:', user.buffer.join(''), 'length:', user.buffer.length);
    
    if (user.buffer.length === 0) {
      console.log('[Decoder] Buffer empty, nothing to flush');
      return;
    }
    
    const pattern = user.buffer.join('');
    const char = this.morseTable[pattern] || '?';
    
    console.log('[Decoder]', callsign, 'DECODED:', pattern, '→', char, 'wpm:', user.wpm);
    
    if (this.onDecodedChar) {
      console.log('[Decoder] Calling onDecodedChar callback');
      this.onDecodedChar(callsign, char, user.wpm);
    } else {
      console.log('[Decoder] ERROR: onDecodedChar callback is not set!');
    }
    
    user.buffer = [];
  }
  
  /**
   * Get user WPM estimate
   */
  getUserWpm(callsign) {
    return this.users.has(callsign) ? this.users.get(callsign).wpm : 0;
  }
  
  /**
   * Remove user
   */
  removeUser(callsign) {
    const user = this.users.get(callsign);
    if (user && user.flushTimer) {
      clearTimeout(user.flushTimer);
    }
    this.users.delete(callsign);
  }
  
  /**
   * Clear all
   */
  clear() {
    // Clear all timers before clearing users
    for (const [callsign, user] of this.users.entries()) {
      if (user.flushTimer) {
        clearTimeout(user.flushTimer);
      }
    }
    this.users.clear();
  }
}
