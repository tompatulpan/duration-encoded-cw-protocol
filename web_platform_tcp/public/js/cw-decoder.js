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
      letterSpaceThreshold: 3.0, // Minimum gap to trigger letter space (between 3T and 4T)
      wordSpaceThreshold: 7.0,   // Minimum gap to trigger word space (7T = standard word space)
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
        avgDit: 60, // Initial estimate (20 WPM)
        wpm: 20,
        lastEventTimestamp: timestamp_ms,
        flushTimer: null
      });
      console.log('[Decoder] New user:', callsign);
    }
    
    const user = this.users.get(callsign);
    
    // Calculate timestamp gap (for timestamp protocol word space detection)
    const timestampGap = timestamp_ms - user.lastEventTimestamp;
    user.lastEventTimestamp = timestamp_ms;
    
    if (key_down) {
      // For timestamp protocol: Check timestamp gap to detect letter/word spaces
      // Morse timing model: intra-symbol space = 1T, letter space = 3T, word space = 7T
      // Use configurable threshold (default 3.5T): between longest within-character gap (4T) and letter space minimum (3T)
      if (timestampGap > user.avgDit * this.TIMING_CONFIG.letterSpaceThreshold) {
        // Word space: configurable threshold (default 7T = standard word space)
        if (timestampGap > user.avgDit * this.TIMING_CONFIG.wordSpaceThreshold) {
          console.log('[Decoder]', callsign, 'word space detected via timestamp gap:', timestampGap + 'ms', '(threshold:', (user.avgDit * this.TIMING_CONFIG.wordSpaceThreshold).toFixed(0) + 'ms)');
          this.flushCharacter(callsign, user);
          if (this.onDecodedWord) {
            this.onDecodedWord(callsign, ' ');
          }
        }
        // Letter space: configurable threshold (default 3.5T)
        else {
          console.log('[Decoder]', callsign, 'letter space detected via timestamp gap:', timestampGap + 'ms', '(threshold:', (user.avgDit * this.TIMING_CONFIG.letterSpaceThreshold).toFixed(0) + 'ms)');
          this.flushCharacter(callsign, user);
        }
      }
      // Otherwise it's intra-symbol space (1T) - continue building current character
      
      // Key down event - duration_ms is how long the key was DOWN (dit or dah)
      const elementDuration = duration_ms;
      
      // Classify as dit or dah
      const threshold = user.avgDit * this.TIMING_CONFIG.ditDahThreshold;
      const isDit = elementDuration < threshold;
      
      user.buffer.push(isDit ? '.' : '-');
      
      // Update average dit time from both dits and dahs (exponential moving average)
      // Dits: use duration directly, Dahs: divide by 3 to get dit equivalent
      const ditEquivalent = isDit ? elementDuration : elementDuration / 3;
      user.avgDit = user.avgDit * this.TIMING_CONFIG.avgDitSmoothFactor + ditEquivalent * (1 - this.TIMING_CONFIG.avgDitSmoothFactor);
      user.wpm = Math.round(1200 / user.avgDit);
      
      console.log('[Decoder]', callsign, 'element:', isDit ? 'dit' : 'dah', elementDuration + 'ms', 'buffer:', user.buffer.join(''), 'wpm:', user.wpm);
    } else {
      // Key up event - duration_ms is the SPACING after the element
      // Morse timing model: intra-symbol space = 1T, letter space = 3T, word space = 7T
      // With timestamp protocol, duration_ms is constant (intra-symbol space) and
      // letter/word spaces are detected via timestamp gaps on DOWN events (above)
      const spaceDuration = duration_ms;
      
      console.log('[Decoder]', callsign, 'space:', spaceDuration + 'ms', 'avgDit:', user.avgDit.toFixed(1) + 'ms');
      
      // Legacy: Also check duration_ms for duration-based protocol compatibility
      // Word space detection: > 5T (between letter space 3T and word space 7T)
      const durationWordThreshold = (this.TIMING_CONFIG.letterSpaceThreshold + this.TIMING_CONFIG.wordSpaceThreshold) / 2; // Midpoint
      if (spaceDuration > user.avgDit * durationWordThreshold) {
        console.log('[Decoder]', callsign, 'word space detected via duration:', spaceDuration + 'ms', '(threshold:', (user.avgDit * durationWordThreshold).toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
        if (this.onDecodedWord) {
          this.onDecodedWord(callsign, ' ');
        }
      }
      // Letter space detection: > ditDahThreshold (between intra-symbol 1T and letter space threshold)
      else if (spaceDuration > user.avgDit * this.TIMING_CONFIG.ditDahThreshold) {
        console.log('[Decoder]', callsign, 'letter space detected via duration:', spaceDuration + 'ms', '(threshold:', (user.avgDit * this.TIMING_CONFIG.ditDahThreshold).toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
      }
      // Otherwise it's intra-symbol space (1T) - continue building current character
      
      // Set timeout to flush last character if no more events come
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
