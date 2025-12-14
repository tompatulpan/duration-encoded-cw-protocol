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
      ditDahThreshold: 1.5,      // Threshold between dit and dah (1.5× dit, matches Python)
      letterSpaceThreshold: 2.5, // Letter space detection 
      wordSpaceThreshold: 6.9,   // Word space detection (standard = 7× dit, detect at 5× with margin)
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
      '-...-': '=', '.-.-.': '+', '-....-': '-', '.--.-.': '@'
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
   * Protocol uses duration_ms to encode timing:
   * - DOWN event: duration_ms = element length (dit or dah)
   * - UP event: duration_ms = spacing (element_space or letter_space)
   */
  processEvent(event) {
    const { callsign, key_down, duration_ms, timestamp_ms } = event;
    
    console.log('[Decoder] Processing event:', callsign, 'key:', key_down, 'dur:', duration_ms, 'ts:', timestamp_ms);
    
    // Get or create user state
    if (!this.users.has(callsign)) {
      this.users.set(callsign, {
        buffer: [],
        avgDit: 50, // Initial estimate (24 WPM middle ground - faster convergence)
        wpm: 20,
        lastEventTimestamp: timestamp_ms,
        lastElementDuration: 0, // Track last element duration for context
        elementCount: 0, // Track elements for adaptive convergence
        flushTimer: null,
        senderTimelineOffset: null, // Synchronized sender timeline (for timestamp protocol)
        lastRecvTime: Date.now() / 1000.0, // Track actual arrival time for gap detection
        consecutiveElementSpaces: 0, // Track manual keying pattern
        isManualKeying: false // Flag for manual paddle keying detection
      });
      console.log('[Decoder] New user:', callsign);
    }
    
    const user = this.users.get(callsign);
    
    // Timestamp-based gap detection (for burst-resistant word spacing)
    const now = Date.now() / 1000.0; // Current time in seconds
    
    // Initialize sender timeline on first packet
    if (user.senderTimelineOffset === null && timestamp_ms !== undefined) {
      user.senderTimelineOffset = now - (timestamp_ms / 1000.0);
      console.log('[Decoder]', callsign, 'Synchronized to sender timeline, offset:', user.senderTimelineOffset.toFixed(3));
    }
    
    // Check for gaps using timestamps (more reliable than arrival time during bursts)
    if (user.lastEventTimestamp !== null && timestamp_ms !== undefined) {
      const timestampGap = timestamp_ms - user.lastEventTimestamp; // Gap in sender's timeline
      const wordSpaceThreshold = user.avgDit * this.TIMING_CONFIG.wordSpaceThreshold;
      
      if (timestampGap > wordSpaceThreshold) {
        // Word space detected via timestamp gap (sender was idle)
        console.log('[Decoder]', callsign, 'WORD SPACE via timestamp gap:', timestampGap.toFixed(0) + 'ms', '(threshold:', wordSpaceThreshold.toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
        if (this.onWordSpace) {
          this.onWordSpace(callsign);
        }
      }
    }
    
    // Update last event timestamp
    if (timestamp_ms !== undefined) {
      user.lastEventTimestamp = timestamp_ms;
    }
    user.lastRecvTime = now;
    
    
    if (key_down) {
      // Key down event - duration_ms is how long the key was DOWN (dit or dah)
      const elementDuration = duration_ms;
      
      // Clear any pending flush timer (new element arriving, not end of character)
      if (user.flushTimer) {
        clearTimeout(user.flushTimer);
        user.flushTimer = null;
      }
      
      // Classify as dit or dah
      const threshold = user.avgDit * this.TIMING_CONFIG.ditDahThreshold;
      const isDit = elementDuration < threshold;
      
      user.buffer.push(isDit ? '.' : '-');
      
      // Store this element's duration for next iteration's context
      user.lastElementDuration = elementDuration;
      
      // Adaptive convergence: faster smoothing initially, then stable
      const smoothFactor = (user.elementCount < 10) ? 0.7 : this.TIMING_CONFIG.avgDitSmoothFactor;
      
      // Update average dit time from both dits and dahs (exponential moving average)
      // Dits: use duration directly, Dahs: divide by 3 to get dit equivalent
      const ditEquivalent = isDit ? elementDuration : elementDuration / 3;
      user.avgDit = user.avgDit * smoothFactor + ditEquivalent * (1 - smoothFactor);
      user.wpm = Math.round(1200 / user.avgDit);
      user.elementCount++; // Increment element counter
      
      console.log('[Decoder]', callsign, 'DOWN event - element:', isDit ? 'dit' : 'dah', elementDuration + 'ms', 'ts:', timestamp_ms + 'ms', 'buffer:', user.buffer.join(''), 'wpm:', user.wpm, 'avgDit:', user.avgDit.toFixed(1) + 'ms', user.isManualKeying ? '(manual)' : '(auto)');
    } else {
      // Key UP event - duration_ms is the SPACING duration
      // This is the CORRECT way to detect character boundaries (like Python decoder)
      const spaceDuration = duration_ms;

      console.log('[Decoder]', callsign, 'UP event - space:', spaceDuration + 'ms', 'ts:', timestamp_ms + 'ms', 'avgDit:', user.avgDit.toFixed(1) + 'ms');

      // Spacing detection based on UP duration (matches Python decoder logic)
      const letterSpaceThreshold = user.avgDit * this.TIMING_CONFIG.letterSpaceThreshold;
      const wordSpaceThreshold = user.avgDit * this.TIMING_CONFIG.wordSpaceThreshold;
      const elementSpaceThreshold = user.avgDit * 1.5; // ~1 dit for element space
      
      // Detect manual keying pattern (consistent element spacing ~1 dit)
      if (spaceDuration < elementSpaceThreshold) {
        user.consecutiveElementSpaces++;
        if (user.consecutiveElementSpaces >= 3 && !user.isManualKeying) {
          user.isManualKeying = true;
          console.log('[Decoder]', callsign, 'Manual paddle keying detected');
        }
      } else {
        // Reset manual keying detection on letter/word space
        if (user.consecutiveElementSpaces > 0) {
          user.consecutiveElementSpaces = 0;
        }
      }

      // DIAGNOSTIC: Log threshold calculations
      console.log('[Decoder] DIAGNOSTIC:', callsign, 
                  'spaceDuration=' + spaceDuration + 'ms',
                  'avgDit=' + user.avgDit.toFixed(1) + 'ms',
                  'letterThreshold=' + letterSpaceThreshold.toFixed(1) + 'ms (' + this.TIMING_CONFIG.letterSpaceThreshold + '× dit)',
                  'wordThreshold=' + wordSpaceThreshold.toFixed(1) + 'ms (' + this.TIMING_CONFIG.wordSpaceThreshold + '× dit)',
                  'buffer=' + user.buffer.join(''),
                  user.isManualKeying ? '(manual)' : '(auto)');

      if (spaceDuration > wordSpaceThreshold) {
        // Word space
        console.log('[Decoder]', callsign, 'WORD SPACE detected:', spaceDuration + 'ms', '(threshold:', wordSpaceThreshold.toFixed(0) + 'ms)', 'avgDit:', user.avgDit.toFixed(1) + 'ms');
        this.flushCharacter(callsign, user);
        user.isManualKeying = false; // Reset on word boundaries
        if (this.onWordSpace) {
          this.onWordSpace(callsign);
        }
      } else if (spaceDuration > letterSpaceThreshold) {
        // Letter space
        console.log('[Decoder]', callsign, 'LETTER SPACE detected:', spaceDuration + 'ms', '(threshold:', letterSpaceThreshold.toFixed(0) + 'ms)', 'avgDit:', user.avgDit.toFixed(1) + 'ms');
        this.flushCharacter(callsign, user);
        user.isManualKeying = false; // Reset on letter boundaries
      } else {
        // Intra-element space - continue building current character
        // Set timeout to flush last character if no more events come (end of transmission)
        // For manual keying, use shorter timeout since spacing is consistent
        const timeoutMs = user.isManualKeying 
          ? letterSpaceThreshold * 1.5 
          : letterSpaceThreshold * 2;
        
        if (user.flushTimer) {
          clearTimeout(user.flushTimer);
        }
        user.flushTimer = setTimeout(() => {
          this.flushCharacter(callsign, user);
          user.isManualKeying = false; // Reset after character completion
        }, timeoutMs);
      }
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
    this.users.clear();
  }
}
