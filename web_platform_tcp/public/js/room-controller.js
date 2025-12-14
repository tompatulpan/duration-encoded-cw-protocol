/**
 * Room Controller
 * 
 * Main application logic - ties together all components.
 * Supports paddle input (Z/X keys) and automated text sending.
 */

// Configuration
const WORKER_URL = location.hostname === 'localhost'
  ? 'ws://localhost:8788'
  : 'wss://cw-studio-relay.data4-9de.workers.dev';

// Parse URL parameters
const urlParams = new URLSearchParams(window.location.search);
const roomId = urlParams.get('room') || 'main';
const callsign = urlParams.get('callsign') || 'TEST';

// Components
let client;
let jitterBuffer;
let audioHandler;
let decoder;

// State
let wpm = 20;
let ditMs = 1200 / wpm;
let isKeying = false;
let keyDownTime = 0;

// Iambic keyer state (Mode B)
let ditPressed = false;
let dahPressed = false;
let keyerState = 'IDLE'; // IDLE, DIT, DAH
let ditMemory = false;
let dahMemory = false;
let keyingLoopActive = false;

// Morse table for text-to-CW
const morseTable = {
  'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',
  'E': '.',     'F': '..-.',  'G': '--.',   'H': '....',
  'I': '..',    'J': '.---',  'K': '-.-',   'L': '.-..',
  'M': '--',    'N': '-.',    'O': '---',   'P': '.--.',
  'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
  'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',
  'Y': '-.--',  'Z': '--..',
  '0': '-----', '1': '.----', '2': '..---', '3': '...--',
  '4': '....-', '5': '.....', '6': '-....', '7': '--...',
  '8': '---..', '9': '----.',
  '.': '.-.-.-', ',': '--..--', '?': '..--..', '/': '-..-.',
  '=': '-...-', '<AR>': '.-.-.', '-': '-....-', '@': '.--.-.',
  // Swedish letters
  'Å': '.--.-', 'Ä': '.-.-', 'Ö': '---.'
  // Note: Prosigns <AR> and <SK> are decoded but not encoded from text
};

/**
 * Initialize application
 */
async function init() {
  console.log(`[Room] Initializing - Room: ${roomId}, Callsign: ${callsign}`);
  
  // Update UI
  document.getElementById('roomName').textContent = `Room: ${roomId}`;
  document.getElementById('callsignDisplay').textContent = `Callsign: ${callsign}`;
  
  // Initialize components
  jitterBuffer = new JitterBuffer(150);
  audioHandler = new AudioHandler();
  decoder = new CWDecoder();
  client = new TCPTSClient(WORKER_URL);
  
  // Setup callbacks
  setupCallbacks();
  
  // Setup UI event listeners
  setupUI();
  
  // Setup audio permission handler
  setupAudioPermission();
  
  // Connect to server
  try {
    await client.connect(roomId, callsign);
    console.log('[Room] Connected successfully');
    updateConnectionStatus(true);
  } catch (error) {
    console.error('[Room] Connection failed:', error);
    updateConnectionStatus(false);
    alert('Failed to connect to server. Please try again.');
  }
}

/**
 * Setup callbacks
 */
function setupCallbacks() {
  // Client callbacks
  client.onConnected = (data) => {
    console.log('[Room] Joined room:', data);
    console.log('[Room] My peer ID:', data.peerId);
    console.log('[Room] Existing peers:', data.peers);
    updateUsersList(data.peers);
  };
  
  client.onPeerJoined = (data) => {
    console.log('[Room] Peer joined:', data.callsign);
    addUser(data.peerId, data.callsign);
  };
  
  client.onPeerLeft = (data) => {
    console.log('[Room] Peer left:', data.callsign, data.peerId);
    removeUser(data.peerId, data.callsign);
  };
  
  client.onCwEvent = (event) => {
    console.log('[Room] Received CW event from:', event.callsign, event.key_down ? 'DOWN' : 'UP');
    // Add to jitter buffer
    jitterBuffer.addEvent(event);
  };
  
  // Jitter buffer callback
  jitterBuffer.onPlayEvent = (event) => {
    console.log('[Room] ===== PLAYOUT EVENT =====');
    console.log('[Room] Playing event from jitter buffer:', event);
    console.log('[Room] Callsign:', event.callsign, 'Key:', event.key_down, 'Duration:', event.duration_ms);
    
    // Only play audio for remote users (not your own echo)
    // Local sidetone is already played immediately in handleKeyDown/Up
    if (event.callsign !== callsign) {
      audioHandler.setKey(event.callsign, event.key_down);
    } else {
      console.log('[Room] Skipping own echo from jitter buffer');
    }
    
    // Decode (for display)
    console.log('[Room] Calling decoder.processEvent()');
    decoder.processEvent(event);
    console.log('[Room] Decoder called');
    
    // Update stats
    updateStats();
  };
  
  // Decoder callbacks
  decoder.onDecodedChar = (callsign, char, wpm) => {
    console.log('[Room] Decoded character:', callsign, char, wpm);
    appendDecodedText(callsign, char, wpm);
  };
  
  decoder.onWordSpace = (callsign) => {
    console.log('[Room] Word space:', callsign);
    appendDecodedText(callsign, ' ', 0);
  };
}

/**
 * Setup UI event listeners
 */
function setupUI() {
  // Manual keying - Dit button (paddle)
  const ditButton = document.getElementById('ditButton');
  ditButton.addEventListener('mousedown', () => handlePaddlePress('dit'));
  ditButton.addEventListener('mouseup', () => handlePaddleRelease('dit'));
  ditButton.addEventListener('touchstart', (e) => { e.preventDefault(); handlePaddlePress('dit'); });
  ditButton.addEventListener('touchend', (e) => { e.preventDefault(); handlePaddleRelease('dit'); });
  
  // Manual keying - Dah button (paddle)
  const dahButton = document.getElementById('dahButton');
  dahButton.addEventListener('mousedown', () => handlePaddlePress('dah'));
  dahButton.addEventListener('mouseup', () => handlePaddleRelease('dah'));
  dahButton.addEventListener('touchstart', (e) => { e.preventDefault(); handlePaddlePress('dah'); });
  dahButton.addEventListener('touchend', (e) => { e.preventDefault(); handlePaddleRelease('dah'); });
  
  // Keyboard shortcuts (,=dit, .=dah)
  document.addEventListener('keydown', (e) => {
    if (e.key === ',' && !ditPressed) {
      e.preventDefault();
      handlePaddlePress('dit');
      ditButton.classList.add('active');
    } else if (e.key === '.' && !dahPressed) {
      e.preventDefault();
      handlePaddlePress('dah');
      dahButton.classList.add('active');
    }
  });
  
  document.addEventListener('keyup', (e) => {
    if (e.key === ',') {
      e.preventDefault();
      handlePaddleRelease('dit');
      ditButton.classList.remove('active');
    } else if (e.key === '.') {
      e.preventDefault();
      handlePaddleRelease('dah');
      dahButton.classList.remove('active');
    }
  });
  
  // WPM slider
  const wpmSlider = document.getElementById('wpmSlider');
  const wpmValue = document.getElementById('wpmValue');
  wpmSlider.addEventListener('input', (e) => {
    wpm = parseInt(e.target.value);
    ditMs = 1200 / wpm;
    wpmValue.textContent = wpm;
  });
  
  // Send text button
  document.getElementById('sendButton').addEventListener('click', () => {
    const text = document.getElementById('textInput').value.trim();
    if (text) {
      sendText(text);
    }
  });
  
  // Practice drills
  document.querySelectorAll('.btn-drill').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.text;
      sendText(text);
    });
  });
  
  // Settings
  document.getElementById('audioEnabled').addEventListener('change', (e) => {
    audioHandler.setEnabled(e.target.checked);
  });
  
  const sidetoneFreq = document.getElementById('sidetoneFreq');
  const freqValue = document.getElementById('freqValue');
  sidetoneFreq.addEventListener('input', (e) => {
    const freq = parseInt(e.target.value);
    audioHandler.setFrequency(freq);
    freqValue.textContent = freq;
  });
  
  const volumeSlider = document.getElementById('volumeSlider');
  const volumeValue = document.getElementById('volumeValue');
  volumeSlider.addEventListener('input', (e) => {
    const volume = parseInt(e.target.value) / 100;
    audioHandler.setVolume(volume);
    volumeValue.textContent = e.target.value;
  });
  
  const bufferSlider = document.getElementById('bufferSlider');
  const bufferValue = document.getElementById('bufferValue');
  bufferSlider.addEventListener('input', (e) => {
    const bufferMs = parseInt(e.target.value);
    jitterBuffer.setBufferSize(bufferMs);
    bufferValue.textContent = bufferMs;
    document.getElementById('statBuffer').textContent = `${bufferMs}ms`;
  });
}

/**
 * Handle paddle press (dit or dah)
 */
async function handlePaddlePress(type) {
  if (type === 'dit') {
    if (ditPressed) return; // Already pressed
    ditPressed = true;
  } else if (type === 'dah') {
    if (dahPressed) return; // Already pressed
    dahPressed = true;
  }
  
  // Start keyer if not already running
  if (!keyingLoopActive) {
    startIambicKeyer();
  }
}

/**
 * Handle paddle release (dit or dah)
 */
function handlePaddleRelease(type) {
  if (type === 'dit') {
    ditPressed = false;
  } else if (type === 'dah') {
    dahPressed = false;
  }
}

/**
 * Iambic Keyer (Mode B) - matches Python implementation
 * Implements proper paddle memory and automatic alternation
 */
async function startIambicKeyer() {
  if (keyingLoopActive) return;
  
  keyingLoopActive = true;
  keyerState = 'IDLE';
  ditMemory = false;
  dahMemory = false;
  
  while (true) {
    // IDLE state - waiting for paddle press
    if (keyerState === 'IDLE') {
      if (ditPressed) {
        ditMemory = false;
        dahMemory = false;
        keyerState = 'DIT';
        
        // Send dit
        await sendElement(ditMs);
        
        // Check if dah was pressed during dit (Mode B memory)
        if (dahPressed) {
          dahMemory = true;
        }
        
      } else if (dahPressed) {
        ditMemory = false;
        dahMemory = false;
        keyerState = 'DAH';
        
        // Send dah
        await sendElement(ditMs * 3);
        
        // Check if dit was pressed during dah (Mode B memory)
        if (ditPressed) {
          ditMemory = true;
        }
        
      } else {
        // No paddles pressed, exit keyer
        break;
      }
    }
    
    // DIT state - just sent a dit
    else if (keyerState === 'DIT') {
      // Sample paddles (memory from element space)
      if (ditPressed) {
        ditMemory = true;
      }
      if (dahPressed) {
        dahMemory = true;
      }
      
      // Decide what's next
      if (dahMemory) {
        dahMemory = false;
        keyerState = 'DAH';
        
        // Send dah
        await sendElement(ditMs * 3);
        
        // Mode B: Check for dit during dah
        if (ditPressed) {
          ditMemory = true;
        }
        
      } else if (ditMemory) {
        ditMemory = false;
        keyerState = 'DIT';
        
        // Send dit
        await sendElement(ditMs);
        
        // Mode B: Check for dah during dit
        if (dahPressed) {
          dahMemory = true;
        }
        
      } else {
        // No memory, return to idle
        keyerState = 'IDLE';
      }
    }
    
    // DAH state - just sent a dah
    else if (keyerState === 'DAH') {
      // Sample paddles (memory from element space)
      if (ditPressed) {
        ditMemory = true;
      }
      if (dahPressed) {
        dahMemory = true;
      }
      
      // Decide what's next
      if (ditMemory) {
        ditMemory = false;
        keyerState = 'DIT';
        
        // Send dit
        await sendElement(ditMs);
        
        // Mode B: Check for dah during dit
        if (dahPressed) {
          dahMemory = true;
        }
        
      } else if (dahMemory) {
        dahMemory = false;
        keyerState = 'DAH';
        
        // Send dah
        await sendElement(ditMs * 3);
        
        // Mode B: Check for dit during dah
        if (ditPressed) {
          ditMemory = true;
        }
        
      } else {
        // No memory, return to idle
        keyerState = 'IDLE';
      }
    }
  }
  
  keyingLoopActive = false;
  keyerState = 'IDLE';
}

/**
 * Send a single CW element (dit or dah)
 */
async function sendElement(duration) {
  // Key down
  client.sendCwEvent(true, duration);
  audioHandler.setKey(callsign, true);
  
  // Also decode our own keying locally
  const downEvent = {
    callsign: callsign,
    key_down: true,
    duration_ms: duration,
    timestamp_ms: Date.now()
  };
  console.log('[Room] Local DOWN event:', downEvent);
  decoder.processEvent(downEvent);
  
  await sleep(duration);
  
  // Key up (element space)
  const elementSpace = ditMs;
  client.sendCwEvent(false, elementSpace);
  audioHandler.setKey(callsign, false);
  
  // Also decode the UP event locally
  const upEvent = {
    callsign: callsign,
    key_down: false,
    duration_ms: elementSpace,
    timestamp_ms: Date.now()
  };
  console.log('[Room] Local UP event:', upEvent);
  decoder.processEvent(upEvent);
  
  await sleep(elementSpace);
}

/**
 * Send text as Morse code
 */
async function sendText(text) {
  console.log('[Room] Sending text:', text);
  
  const words = text.toUpperCase().split(' ');
  
  for (let wordIdx = 0; wordIdx < words.length; wordIdx++) {
    const word = words[wordIdx];
    
    for (let charIdx = 0; charIdx < word.length; charIdx++) {
      const char = word[charIdx];
      const pattern = morseTable[char];
      
      if (!pattern) continue;
      
      // Send each element in pattern
      for (let i = 0; i < pattern.length; i++) {
        const isDit = pattern[i] === '.';
        const duration = isDit ? ditMs : ditMs * 3;
        
        // Key down
        client.sendCwEvent(true, duration);
        audioHandler.setKey(callsign, true);
        
        // Decode locally
        decoder.processEvent({
          callsign: callsign,
          key_down: true,
          duration_ms: duration,
          timestamp_ms: Date.now()
        });
        
        await sleep(duration);
        
        // Key up - send element space or letter space
        const isLastElement = (i === pattern.length - 1);
        const space = isLastElement ? (ditMs * 3) : ditMs; // Letter space (3 units) or element space (1 unit)
        client.sendCwEvent(false, space);
        audioHandler.setKey(callsign, false);
        
        // Decode locally
        decoder.processEvent({
          callsign: callsign,
          key_down: false,
          duration_ms: space,
          timestamp_ms: Date.now()
        });
        
        await sleep(space);
      }
    }
    
    // Word space (send 7 dit units total as event)
    if (wordIdx < words.length - 1) {
      const wordSpace = ditMs * 7; // Full word space
      client.sendCwEvent(false, wordSpace);
      
      // Decode word space locally
      decoder.processEvent({
        callsign: callsign,
        key_down: false,
        duration_ms: wordSpace,
        timestamp_ms: Date.now()
      });
      
      await sleep(wordSpace);
    }
  }
  
  console.log('[Room] Text sent');
}

/**
 * Update connection status
 */
function updateConnectionStatus(connected) {
  const status = document.getElementById('connectionStatus');
  status.textContent = connected ? 'Connected' : 'Disconnected';
  status.className = `status ${connected ? 'connected' : 'disconnected'}`;
}

/**
 * Update users list
 */
function updateUsersList(peers) {
  const usersList = document.getElementById('usersList');
  
  if (!peers || peers.length === 0) {
    usersList.innerHTML = '<p>No other users yet</p>';
    return;
  }
  
  let html = '';
  peers.forEach(peer => {
    html += `<div class="user-item" data-peer-id="${peer.peerId}">${peer.callsign}</div>`;
  });
  
  usersList.innerHTML = html;
}

/**
 * Add user to list
 */
function addUser(peerId, callsign) {
  const usersList = document.getElementById('usersList');
  
  if (usersList.querySelector('p')) {
    usersList.innerHTML = '';
  }
  
  const userItem = document.createElement('div');
  userItem.className = 'user-item';
  userItem.dataset.peerId = peerId;
  userItem.textContent = callsign;
  
  usersList.appendChild(userItem);
}

/**
 * Remove user from list
 */
function removeUser(peerId, callsign) {
  const userItem = document.querySelector(`[data-peer-id="${peerId}"]`);
  if (userItem) {
    userItem.remove();
  }
  
  // Check if list is empty
  const usersList = document.getElementById('usersList');
  if (usersList.children.length === 0) {
    usersList.innerHTML = '<p>No other users yet</p>';
  }
  
  // Cleanup audio, decoder, and jitter buffer
  if (callsign) {
    console.log('[Room] Cleaning up state for:', callsign);
    audioHandler.removeUser(callsign);
    decoder.removeUser(callsign);
    jitterBuffer.removeSender(callsign);
  }
}

/**
 * Append decoded text
 */
function appendDecodedText(callsign, text, wpm) {
  const output = document.getElementById('decoderOutput');
  
  // Find or create entry for this callsign
  let entry = output.querySelector(`[data-callsign="${callsign}"]`);
  
  if (!entry) {
    // Create new entry for this callsign
    entry = document.createElement('div');
    entry.className = 'decoder-entry';
    entry.dataset.callsign = callsign;
    
    const callsignSpan = document.createElement('span');
    callsignSpan.className = 'callsign';
    callsignSpan.textContent = callsign + ': ';
    
    const textSpan = document.createElement('span');
    textSpan.className = 'text';
    textSpan.textContent = '';
    
    const wpmSpan = document.createElement('span');
    wpmSpan.className = 'wpm';
    wpmSpan.textContent = '';
    
    entry.appendChild(callsignSpan);
    entry.appendChild(textSpan);
    entry.appendChild(wpmSpan);
    
    output.appendChild(entry);
  }
  
  // Append text to existing entry
  const textSpan = entry.querySelector('.text');
  const wpmSpan = entry.querySelector('.wpm');
  
  // Check if text is a word space (empty or whitespace)
  if (text.trim() === '') {
    // Word space - add space if not already ending with space
    if (!textSpan.textContent.endsWith(' ')) {
      textSpan.textContent += ' ';
    }
  } else {
    // Regular character - append
    textSpan.textContent += text;
  }
  
  // Update WPM indicator (show latest)
  if (wpm > 0) {
    wpmSpan.textContent = ` (${wpm} WPM)`;
  }
  
  // Auto-scroll to bottom
  output.scrollTop = output.scrollHeight;
  
  // Limit total text length per callsign (keep last 500 chars)
  if (textSpan.textContent.length > 500) {
    textSpan.textContent = '...' + textSpan.textContent.slice(-500);
  }
  
  // Limit number of callsign entries (keep last 10)
  while (output.children.length > 10) {
    output.firstChild.remove();
  }
  
  // Limit entries (keep last 100)
  while (output.children.length > 100) {
    output.firstChild.remove();
  }
}

/**
 * Setup audio permission handler
 */
function setupAudioPermission() {
  const banner = document.getElementById('audioPermissionBanner');
  const enableBtn = document.getElementById('enableAudioBtn');
  
  // Check if audio context is suspended
  if (audioHandler.audioContext && audioHandler.audioContext.state === 'suspended') {
    banner.style.display = 'block';
  }
  
  // Enable audio on click
  const enableAudio = async () => {
    await audioHandler.resume();
    banner.style.display = 'none';
    console.log('[Room] Audio enabled by user');
  };
  
  enableBtn.addEventListener('click', enableAudio);
  document.body.addEventListener('click', enableAudio, { once: true });
  document.body.addEventListener('keydown', enableAudio, { once: true });
}

/**
 * Update statistics
 */
function updateStats() {
  const clientStats = client.getStats();
  const bufferStats = jitterBuffer.getStats();
  
  document.getElementById('statEventsSent').textContent = clientStats.eventsSent;
  document.getElementById('statEventsReceived').textContent = clientStats.eventsReceived;
  document.getElementById('statQueueDepth').textContent = bufferStats.queueDepth;
}

/**
 * Sleep utility
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  if (client) {
    client.disconnect();
  }
  if (audioHandler) {
    audioHandler.destroy();
  }
});

// Initialize on load
window.addEventListener('DOMContentLoaded', init);

// Update stats periodically
setInterval(updateStats, 1000);
