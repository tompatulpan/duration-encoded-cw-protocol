/**
 * CW Decoder
 * 
 * Decodes Morse code events to text with adaptive timing.
 */

class CWDecoder {
  constructor() {
    // Timing thresholds (in multiples of dit duration)
    // Adjust these values to tune decoder sensitivity
    this.TIMING_CONFIG = {
      ditDahThreshold: 2.0,      // Threshold between dit and dah (2× dit = dah boundary)
      letterSpaceThreshold: 2.5, // Letter space detection (2.5T = 120ms @ 25 WPM, catches std 3T=144ms)
      wordSpaceThreshold: 5.0,   // Word space detection (5T = 240ms @ 25 WPM, catches std 7T=336ms)
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
        flushTimer: null
      });
      console.log('[Decoder] New user:', callsign);
    }
    
    const user = this.users.get(callsign);
    
    
    if (key_down) {
      // Key down event - duration_ms is how long the key was DOWN (dit or dah)
      const elementDuration = duration_ms;
      
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
      
      console.log('[Decoder]', callsign, 'DOWN event - element:', isDit ? 'dit' : 'dah', elementDuration + 'ms', 'buffer:', user.buffer.join(''), 'wpm:', user.wpm, 'avgDit:', user.avgDit.toFixed(1) + 'ms');
    } else {
      // Key UP event - duration_ms is the SPACING duration
      // This is the CORRECT way to detect character boundaries (like Python decoder)
      const spaceDuration = duration_ms;

      console.log('[Decoder]', callsign, 'UP event - space:', spaceDuration + 'ms', 'avgDit:', user.avgDit.toFixed(1) + 'ms');

      // Spacing detection based on UP duration (matches Python decoder logic)
      const letterSpaceThreshold = user.avgDit * this.TIMING_CONFIG.letterSpaceThreshold;
      const wordSpaceThreshold = user.avgDit * this.TIMING_CONFIG.wordSpaceThreshold;

      if (spaceDuration > wordSpaceThreshold) {
        // Word space
        console.log('[Decoder]', callsign, 'WORD SPACE detected:', spaceDuration + 'ms', '(threshold:', wordSpaceThreshold.toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
        if (this.onWordSpace) {
          this.onWordSpace(callsign);
        }
      } else if (spaceDuration > letterSpaceThreshold) {
        // Letter space
        console.log('[Decoder]', callsign, 'LETTER SPACE detected:', spaceDuration + 'ms', '(threshold:', letterSpaceThreshold.toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
      }
      // Otherwise intra-element space - continue building current character

      // Set timeout to flush last character if no more events come (end of transmission)
      if (user.flushTimer) {
        clearTimeout(user.flushTimer);
      }
      user.flushTimer = setTimeout(() => {
        this.flushCharacter(callsign, user);
      }, user.avgDit * 5); // Flush after 5× dit of inactivity
    }
  }
  
  /**
   * Flush current character buffer
   */
  flushCharacter(callsign, user) {
    if (user.buffer.length === 0) return;
    
    const pattern = user.buffer.join('');
    const char = this.morseTable[pattern] || '?';
    
    if (this.onDecodedChar) {
      this.onDecodedChar(callsign, char, user.wpm);
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
