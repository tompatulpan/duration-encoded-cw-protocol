/**
 * CW Morse Code Decoder
 * JavaScript port of the Python MorseDecoder
 */

class MorseDecoder {
    // International Morse Code table
    static MORSE_CODE = {
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
        
        '.-.-.-': '.', '--..--': ',', '..--..': '?', '.----.': "'",
        '-.-.--': '!', '-..-.': '/', '-.--.': '(', '-.--.-': ')',
        '.-...': '&', '---...': ':', '-.-.-.': ';', '-...-': '=',
        '.-.-.': '+', '-....-': '-', '..--.-': '_', '.-..-.': '"',
        '...-..-': '$', '.--.-.': '@',
        
        // Prosigns (procedural signals)
        '...---...': '<SOS>',
        '.-.-.': '<AR>',
        '-...-.-': '<BT>',
        '........': '<HH>',
        '-.--.': '<KN>',
        '...-.-': '<SK>',
        '-.-.-': '<KA>'
    };

    constructor(wpm = 20) {
        this.wpm = wpm;
        this.dit_duration = 1200 / wpm;  // ms
        this.current_pattern = '';
        this.decoded_text = '';
        this.last_element_time = null;
        this.last_spacing_check = 0;
        
        // Timing thresholds (in milliseconds)
        this.dit_threshold = this.dit_duration * 1.5;  // < 1.5 dits = dit
        this.char_space = this.dit_duration * 3.5;     // ~3.5 dit spaces = character boundary
        this.word_space = this.dit_duration * 7;       // ~7 dit spaces = word boundary
        
        // Statistics
        this.char_count = 0;
        this.word_count = 0;
        this.dit_times = [];
        this.dah_times = [];
    }

    /**
     * Add a dit or dah based on key-down duration
     */
    addElement(duration_ms) {
        // Determine if dit or dah
        if (duration_ms < this.dit_threshold) {
            this.current_pattern += '.';
            this.dit_times.push(duration_ms);
        } else {
            this.current_pattern += '-';
            this.dah_times.push(duration_ms);
        }
        
        // Keep only recent measurements for WPM estimation
        if (this.dit_times.length > 20) this.dit_times.shift();
        if (this.dah_times.length > 20) this.dah_times.shift();
        
        this.last_element_time = Date.now();
        this.last_spacing_check = 0;
    }

    /**
     * Check if silence indicates character or word boundary
     * Returns: { type: 'word'|'char'|null, character: string|null }
     */
    checkSpacing(silence_ms) {
        if (!this.current_pattern) {
            return { type: null, character: null };
        }
        
        // Prevent repeated triggering on same silence period
        if (silence_ms <= this.last_spacing_check) {
            return { type: null, character: null };
        }
        
        // Word space
        if (silence_ms > this.word_space) {
            this.last_spacing_check = silence_ms;
            const char = this._finishCharacter();
            if (char) {
                this.decoded_text += ' ';
                this.word_count++;
                return { type: 'word', character: char };
            }
            return { type: null, character: null };
        }
        
        // Character space
        else if (silence_ms > this.char_space) {
            this.last_spacing_check = silence_ms;
            const char = this._finishCharacter();
            if (char) {
                return { type: 'char', character: char };
            }
            return { type: null, character: null };
        }
        
        return { type: null, character: null };
    }

    /**
     * Convert current pattern to character
     */
    _finishCharacter() {
        if (this.current_pattern) {
            const char = MorseDecoder.MORSE_CODE[this.current_pattern] || '?';
            this.decoded_text += char;
            this.current_pattern = '';
            this.char_count++;
            return char;
        }
        return null;
    }

    /**
     * Force finish any pending character
     */
    finish() {
        if (this.current_pattern) {
            return this._finishCharacter();
        }
        return null;
    }

    /**
     * Get the decoded text so far
     */
    getDecodedText() {
        return this.decoded_text;
    }

    /**
     * Estimate WPM based on recent dit timings
     */
    estimateWPM() {
        if (this.dit_times.length < 5) {
            return this.wpm;  // Return configured WPM if not enough data
        }
        
        // Average dit duration
        const avg_dit = this.dit_times.reduce((a, b) => a + b, 0) / this.dit_times.length;
        
        // WPM = 1200 / dit_duration_ms
        return Math.round(1200 / avg_dit);
    }

    /**
     * Get current statistics
     */
    getStats() {
        return {
            characters: this.char_count,
            words: this.word_count,
            estimatedWPM: this.estimateWPM(),
            currentPattern: this.current_pattern
        };
    }

    /**
     * Reset decoder state
     */
    reset() {
        this.finish();
        this.current_pattern = '';
        this.last_element_time = null;
        this.last_spacing_check = 0;
    }

    /**
     * Clear all decoded text and statistics
     */
    clear() {
        this.decoded_text = '';
        this.current_pattern = '';
        this.char_count = 0;
        this.word_count = 0;
        this.dit_times = [];
        this.dah_times = [];
        this.last_element_time = null;
        this.last_spacing_check = 0;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MorseDecoder;
}
