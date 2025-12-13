/**
 * CW Decoder
 * 
 * Decodes Morse code events to text with adaptive timing.
 */

class CWDecoder {
  constructor() {
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
      // Only check if gap is larger than a full dit+dah cycle (4× dit = dit + element_space + dah + element_space)
      // This avoids false detection during normal character formation
      if (timestampGap > user.avgDit * 4) {
        // Word space: > 6× dit (accounts for letter space threshold)
        if (timestampGap > user.avgDit * 6) {
          console.log('[Decoder]', callsign, 'word space detected via timestamp gap:', timestampGap + 'ms', '(threshold:', (user.avgDit * 6).toFixed(0) + 'ms)');
          this.flushCharacter(callsign, user);
          if (this.onDecodedWord) {
            this.onDecodedWord(callsign, ' ');
          }
        }
        // Letter space: > 4× dit (just finished a character)
        else {
          console.log('[Decoder]', callsign, 'letter space detected via timestamp gap:', timestampGap + 'ms', '(threshold:', (user.avgDit * 4).toFixed(0) + 'ms)');
          this.flushCharacter(callsign, user);
        }
      }
      
      // Key down event - duration_ms is how long the key was DOWN (dit or dah)
      const elementDuration = duration_ms;
      
      // Classify as dit or dah
      const threshold = user.avgDit * 2; // Threshold at 2x dit length
      const isDit = elementDuration < threshold;
      
      user.buffer.push(isDit ? '.' : '-');
      
      // Update average dit time (exponential moving average)
      if (isDit) {
        user.avgDit = user.avgDit * 0.9 + elementDuration * 0.1;
        user.wpm = Math.round(1200 / user.avgDit);
      }
      
      console.log('[Decoder]', callsign, 'element:', isDit ? 'dit' : 'dah', elementDuration + 'ms', 'buffer:', user.buffer.join(''), 'wpm:', user.wpm);
    } else {
      // Key up event - duration_ms is the SPACING after the element
      // With timestamp protocol, spacing is constant (element_space) and word spaces 
      // are detected via timestamp gaps on DOWN events (above)
      const spaceDuration = duration_ms;
      
      console.log('[Decoder]', callsign, 'space:', spaceDuration + 'ms', 'avgDit:', user.avgDit.toFixed(1) + 'ms');
      
      // Legacy: Also check duration_ms for duration-based protocol compatibility
      // Word space detection: > 5× dit (between letter_space and word_space)
      if (spaceDuration > user.avgDit * 5) {
        console.log('[Decoder]', callsign, 'word space detected via duration:', spaceDuration + 'ms', '(threshold:', (user.avgDit * 5).toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
        if (this.onDecodedWord) {
          this.onDecodedWord(callsign, ' ');
        }
      }
      // Letter space detection: > 2× dit (between element_space and letter_space)
      else if (spaceDuration > user.avgDit * 2) {
        console.log('[Decoder]', callsign, 'letter space detected via duration:', spaceDuration + 'ms', '(threshold:', (user.avgDit * 2).toFixed(0) + 'ms)');
        this.flushCharacter(callsign, user);
      }
      // Otherwise it's element_space (1× dit) - continue building current character
      
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
