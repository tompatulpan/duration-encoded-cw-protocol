/**
 * Landing Page Controller
 */

// Configuration
const WORKER_URL = location.hostname === 'localhost' 
  ? 'ws://localhost:8787'
  : 'wss://cw-studio-relay.your-subdomain.workers.dev';

// DOM Elements
const callsignInput = document.getElementById('callsign');
const roomNameInput = document.getElementById('roomName');
const joinButton = document.getElementById('joinButton');
const roomsList = document.getElementById('roomsList');

// Load active rooms
async function loadActiveRooms() {
  try {
    const apiUrl = WORKER_URL.replace('ws://', 'http://').replace('wss://', 'https://') + '/api/rooms';
    const response = await fetch(apiUrl);
    const data = await response.json();
    
    if (data.rooms.length === 0) {
      roomsList.innerHTML = '<p>No active rooms. Be the first to join!</p>';
      return;
    }
    
    let html = '';
    data.rooms.forEach(room => {
      html += `
        <div class="room-card">
          <h3>${room.roomId}</h3>
          <p>${room.operatorCount} operator(s)</p>
          <p class="operators">${room.operators.join(', ')}</p>
          <button class="btn-secondary" onclick="joinRoom('${room.roomId}')">Join</button>
        </div>
      `;
    });
    
    roomsList.innerHTML = html;
  } catch (error) {
    console.error('Failed to load rooms:', error);
    roomsList.innerHTML = '<p>Failed to load rooms</p>';
  }
}

// Join room from card
window.joinRoom = function(roomId) {
  roomNameInput.value = roomId;
  if (callsignInput.value.trim()) {
    joinRoomAction();
  } else {
    callsignInput.focus();
  }
};

// Join room action
function joinRoomAction() {
  const callsign = callsignInput.value.trim().toUpperCase();
  const roomName = roomNameInput.value.trim() || 'main';
  
  if (!callsign) {
    alert('Please enter your callsign');
    callsignInput.focus();
    return;
  }
  
  // Validate callsign (basic)
  if (callsign.length < 3 || callsign.length > 10) {
    alert('Callsign must be 3-10 characters');
    return;
  }
  
  // Navigate to room
  window.location.href = `room.html?room=${encodeURIComponent(roomName)}&callsign=${encodeURIComponent(callsign)}`;
}

// Event listeners
joinButton.addEventListener('click', joinRoomAction);

callsignInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    joinRoomAction();
  }
});

roomNameInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    joinRoomAction();
  }
});

// Load rooms on page load
loadActiveRooms();

// Reload rooms every 10 seconds
setInterval(loadActiveRooms, 10000);

// Focus callsign input
callsignInput.focus();
