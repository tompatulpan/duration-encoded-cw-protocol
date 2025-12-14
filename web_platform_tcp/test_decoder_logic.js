#!/usr/bin/env node
/**
 * Test CW Decoder Logic
 * 
 * Simulates CW events and verifies decoding matches expected output
 */

const fs = require('fs');
const path = require('path');

// Load the decoder
const decoderCode = fs.readFileSync(
  path.join(__dirname, 'public/js/cw-decoder.js'),
  'utf8'
);

// Inject into Node.js environment
eval(decoderCode);

// Test configuration
const WPM = 25;
const DIT_MS = 1200 / WPM;  // 48ms at 25 WPM
const DAH_MS = DIT_MS * 3;   // 144ms
const ELEMENT_SPACE_MS = DIT_MS;      // 48ms
const LETTER_SPACE_MS = DIT_MS * 3;   // 144ms
const WORD_SPACE_MS = DIT_MS * 7;     // 336ms

console.log('CW Decoder Logic Test');
console.log('===================');
console.log(`WPM: ${WPM}`);
console.log(`Dit: ${DIT_MS}ms, Dah: ${DAH_MS}ms`);
console.log(`Element space: ${ELEMENT_SPACE_MS}ms`);
console.log(`Letter space: ${LETTER_SPACE_MS}ms`);
console.log(`Word space: ${WORD_SPACE_MS}ms`);
console.log('');

// Morse patterns
const MORSE_PATTERNS = {
  'S': [DIT_MS, DIT_MS, DIT_MS],           // ...
  'M': [DAH_MS, DAH_MS],                    // --
  'P': [DIT_MS, DAH_MS, DAH_MS, DIT_MS],   // .--.
  'A': [DIT_MS, DAH_MS],                    // .-
  'R': [DIT_MS, DAH_MS, DIT_MS],           // .-.
  'I': [DIT_MS, DIT_MS],                    // ..
};

// Create decoder
const decoder = new CWDecoder();

// Collect decoded output
let decodedText = '';
let decodedChars = [];

decoder.onDecodedChar = (callsign, char, wpm) => {
  decodedText += char;
  decodedChars.push({ char, wpm });
  console.log(`  → Decoded: '${char}' (${wpm} WPM)`);
};

decoder.onWordSpace = (callsign) => {
  decodedText += ' ';
  console.log(`  → Word space`);
};

/**
 * Send a complete character
 */
function sendCharacter(char, elements, isLastInWord = false) {
  console.log(`\nSending '${char}' (${elements.map(d => d === DIT_MS ? 'dit' : 'dah').join('-')})`);
  
  for (let i = 0; i < elements.length; i++) {
    const duration = elements[i];
    const isLastElement = (i === elements.length - 1);
    
    // Send DOWN event (dit or dah)
    const downEvent = {
      callsign: 'TEST',
      key_down: true,
      duration_ms: duration,
      timestamp_ms: Date.now()
    };
    decoder.processEvent(downEvent);
    console.log(`  DOWN ${duration}ms (${duration === DIT_MS ? 'dit' : 'dah'})`);
    
    // Send UP event (spacing)
    let spaceDuration;
    if (!isLastElement) {
      // Between elements in same character
      spaceDuration = ELEMENT_SPACE_MS;
    } else if (isLastInWord) {
      // End of word
      spaceDuration = WORD_SPACE_MS;
    } else {
      // End of character
      spaceDuration = LETTER_SPACE_MS;
    }
    
    const upEvent = {
      callsign: 'TEST',
      key_down: false,
      duration_ms: spaceDuration,
      timestamp_ms: Date.now()
    };
    decoder.processEvent(upEvent);
    
    const spaceType = spaceDuration === ELEMENT_SPACE_MS ? 'element' :
                      spaceDuration === LETTER_SPACE_MS ? 'letter' : 'word';
    console.log(`  UP ${spaceDuration}ms (${spaceType} space)`);
  }
}

/**
 * Run test
 */
function runTest(testName, expected) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`TEST: ${testName}`);
  console.log(`Expected: "${expected}"`);
  console.log(`${'='.repeat(60)}`);
  
  decodedText = '';
  decodedChars = [];
  decoder.clear();
  
  // Run test
  testName === 'SM' && test_SM();
  testName === 'PARIS' && test_PARIS();
  testName === 'PARIS PARIS' && test_PARIS_PARIS();
  
  // Wait for flush timer
  setTimeout(() => {
    console.log(`\n${'='.repeat(60)}`);
    console.log(`RESULT: "${decodedText}"`);
    console.log(`Expected: "${expected}"`);
    console.log(`Status: ${decodedText === expected ? '✓ PASS' : '✗ FAIL'}`);
    console.log(`${'='.repeat(60)}\n`);
    
    if (decodedText !== expected) {
      console.error(`ERROR: Expected "${expected}" but got "${decodedText}"`);
      process.exit(1);
    }
  }, 500);
}

function test_SM() {
  sendCharacter('S', MORSE_PATTERNS['S'], false);  // ... (letter space after)
  sendCharacter('M', MORSE_PATTERNS['M'], true);   // -- (word space after)
}

function test_PARIS() {
  sendCharacter('P', MORSE_PATTERNS['P'], false);
  sendCharacter('A', MORSE_PATTERNS['A'], false);
  sendCharacter('R', MORSE_PATTERNS['R'], false);
  sendCharacter('I', MORSE_PATTERNS['I'], false);
  sendCharacter('S', MORSE_PATTERNS['S'], true);
}

function test_PARIS_PARIS() {
  sendCharacter('P', MORSE_PATTERNS['P'], false);
  sendCharacter('A', MORSE_PATTERNS['A'], false);
  sendCharacter('R', MORSE_PATTERNS['R'], false);
  sendCharacter('I', MORSE_PATTERNS['I'], false);
  sendCharacter('S', MORSE_PATTERNS['S'], true);  // Word space
  
  sendCharacter('P', MORSE_PATTERNS['P'], false);
  sendCharacter('A', MORSE_PATTERNS['A'], false);
  sendCharacter('R', MORSE_PATTERNS['R'], false);
  sendCharacter('I', MORSE_PATTERNS['I'], false);
  sendCharacter('S', MORSE_PATTERNS['S'], true);
}

// Run tests sequentially
runTest('SM', 'SM ');

setTimeout(() => {
  runTest('PARIS', 'PARIS ');
}, 1000);

setTimeout(() => {
  runTest('PARIS PARIS', 'PARIS PARIS ');
}, 2000);

setTimeout(() => {
  console.log('\n✓ All tests passed!');
  process.exit(0);
}, 3000);
