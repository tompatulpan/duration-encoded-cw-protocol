// Landing page JavaScript
// Handles room joining, active rooms display, and UTC clock

// Update UTC clock
function updateUTCClock() {
    const now = new Date();
    const utcTime = now.toUTCString().split(' ')[4];
    document.getElementById('utcTime').textContent = `${utcTime} UTC`;
}

// Load active rooms from signaling server
async function loadActiveRooms() {
    try {
        // TODO: Connect to signaling server to get active rooms
        // For now, show placeholder
        const roomsList = document.getElementById('roomsList');
        roomsList.innerHTML = `
            <div class="room-item">
                <div class="room-name">main</div>
                <div class="room-info">
                    <span class="operator-count">🟢 3 operators</span>
                </div>
            </div>
            <p class="hint">More rooms will appear as operators join</p>
        `;
    } catch (error) {
        console.error('Failed to load rooms:', error);
        document.getElementById('roomsList').innerHTML = 
            '<p class="error">Unable to load active rooms</p>';
    }
}

// Validate callsign format
function validateCallsign(callsign) {
    if (!callsign || callsign.length < 3) {
        return false;
    }
    // Basic validation: alphanumeric, may contain /
    return /^[A-Z0-9\/]+$/i.test(callsign);
}

// Join room button handler
function joinRoom() {
    const callsign = document.getElementById('callsign').value.trim().toUpperCase();
    const roomName = document.getElementById('roomName').value.trim().toLowerCase() || 'main';
    
    if (!validateCallsign(callsign)) {
        alert('Please enter a valid callsign (e.g., SM0ONR, W1ABC)');
        return;
    }
    
    // Store callsign in localStorage for next visit
    localStorage.setItem('cw_callsign', callsign);
    
    // Redirect to room page
    window.location.href = `room.html?room=${encodeURIComponent(roomName)}&callsign=${encodeURIComponent(callsign)}`;
}

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    // Load saved callsign if exists
    const savedCallsign = localStorage.getItem('cw_callsign');
    if (savedCallsign) {
        document.getElementById('callsign').value = savedCallsign;
    }
    
    // Setup join button
    document.getElementById('joinButton').addEventListener('click', joinRoom);
    
    // Allow Enter key to join
    document.getElementById('callsign').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') joinRoom();
    });
    document.getElementById('roomName').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') joinRoom();
    });
    
    // Start UTC clock
    updateUTCClock();
    setInterval(updateUTCClock, 1000);
    
    // Load active rooms
    loadActiveRooms();
    setInterval(loadActiveRooms, 30000); // Refresh every 30 seconds
});
