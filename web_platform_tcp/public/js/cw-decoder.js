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
   */
  processEvent(event) {
    const { callsign, key_down, duration_ms } = event;
    
    console.log('[Decoder] Processing event:', callsign, 'key:', key_down, 'dur:', duration_ms);
    
    // Get or create user state
    if (!this.users.has(callsign)) {
      this.users.set(callsign, {
        buffer: [],
        avgDit: 60, // Initial estimate (20 WPM)
        wpm: 20
      });
      console.log('[Decoder] New user:', callsign);
    }
    
    const user = this.users.get(callsign);
    
    if (key_down) {
      // Key down event - duration_ms is how long the key was DOWN
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
      // Key up event - duration_ms is how long the key was UP (space)
      const spaceDuration = duration_ms;
      
      console.log('[Decoder]', callsign, 'space:', spaceDuration + 'ms', 'avgDit:', user.avgDit);
      
      if (spaceDuration > user.avgDit * 5) {
        // Word space (7 dit units)
        this.flushCharacter(callsign, user);
        if (this.onDecodedWord) {
          this.onDecodedWord(callsign, ' ');
        }
        console.log('[Decoder]', callsign, 'word space detected');
      } else if (spaceDuration > user.avgDit * 2.5) {
        // Letter space (3 dit units)
        this.flushCharacter(callsign, user);
        console.log('[Decoder]', callsign, 'letter space detected');
      }
      // else: element space (1 dit unit) - continue building character
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
    this.users.delete(callsign);
  }
  
  /**
   * Clear all
   */
  clear() {
    this.users.clear();
  }
}
