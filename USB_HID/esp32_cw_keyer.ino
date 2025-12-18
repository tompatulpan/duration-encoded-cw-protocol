/*
 * ESP32 Ethernet CW Keyer - Main Firmware
 * 
 * Standalone network-connected CW keyer using WT32-ETH01 module.
 * Reads paddle inputs via GPIO, runs iambic keyer, sends TCP-TS packets.
 * 
 * Hardware: ESP32-WT32-ETH01 (LAN8720 Ethernet PHY)
 * Protocol: TCP with timestamps (TCP-TS)
 * Receiver: test_implementation/cw_receiver_tcp_ts.py
 * 
 * Pin assignments:
 *   GPIO 2  - Dit paddle input (internal pull-up, active-low)
 *   GPIO 4  - Dah paddle input (internal pull-up, active-low)
 *   GPIO 12 - Sidetone PWM output (600Hz, optional)
 *   GPIO 13 - Config button (hold for WiFi AP mode)
 *   GPIO 15 - Status LED (connection indicator)
 */

#include <ETH.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <Preferences.h>

// ============================================================================
// CONFIGURATION
// ============================================================================

// Pin definitions
const int DIT_PIN = 2;              // Dit paddle input
const int DAH_PIN = 4;              // Dah paddle input
const int SIDETONE_PIN = 12;        // PWM sidetone output
const int CONFIG_BUTTON = 13;       // Configuration button
const int STATUS_LED = 15;          // Status LED

// Network defaults
#define DEFAULT_RECEIVER_IP   "192.168.1.100"
#define DEFAULT_RECEIVER_PORT 7356
#define TCP_TIMEOUT_MS        5000

// CW timing defaults
#define DEFAULT_WPM           20      // Words per minute
#define DIT_DURATION(wpm)     (1200 / (wpm))  // Milliseconds

// Protocol constants
#define TCP_TS_PROTOCOL_VERSION 1
#define MAX_SEQUENCE_NUMBER     256

// Sidetone settings
#define SIDETONE_FREQ         600     // Hz (TX frequency)
#define SIDETONE_CHANNEL      0       // PWM channel
#define SIDETONE_RESOLUTION   8       // 8-bit PWM

// ============================================================================
// GLOBAL STATE
// ============================================================================

// Network
WiFiClient tcpClient;
IPAddress receiverIP;
uint16_t receiverPort = DEFAULT_RECEIVER_PORT;
bool connected = false;

// Configuration storage
Preferences prefs;

// CW keyer state
enum KeyerMode { STRAIGHT_KEY, IAMBIC_A, IAMBIC_B, BUG };
KeyerMode keyerMode = IAMBIC_B;

enum KeyerState { IDLE, DIT, DAH };
KeyerState keyerState = IDLE;

int wpm = DEFAULT_WPM;
unsigned long ditDuration;
unsigned long dahDuration;

bool ditMemory = false;
bool dahMemory = false;

// Protocol state
uint8_t sequenceNumber = 0;
unsigned long transmissionStart = 0;
unsigned long lastEventTime = 0;
bool lastKeyState = false;

// Paddle state
bool ditPaddle = false;
bool dahPaddle = false;
bool lastDitPaddle = false;
bool lastDahPaddle = false;

// Sidetone
bool sidetoneEnabled = true;

// ============================================================================
// SETUP
// ============================================================================

void setup() {
    // Serial for debugging
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n\n=== ESP32 Ethernet CW Keyer ===");
    Serial.println("Version: 1.0.0");
    
    // Initialize GPIO
    pinMode(DIT_PIN, INPUT_PULLUP);
    pinMode(DAH_PIN, INPUT_PULLUP);
    pinMode(CONFIG_BUTTON, INPUT_PULLUP);
    pinMode(STATUS_LED, OUTPUT);
    digitalWrite(STATUS_LED, LOW);
    
    // Initialize sidetone PWM
    if (sidetoneEnabled) {
        ledcSetup(SIDETONE_CHANNEL, SIDETONE_FREQ, SIDETONE_RESOLUTION);
        ledcAttachPin(SIDETONE_PIN, SIDETONE_CHANNEL);
        ledcWrite(SIDETONE_CHANNEL, 0);  // Start silent
    }
    
    // Load configuration from EEPROM
    loadConfiguration();
    
    // Calculate timing
    calculateTimings();
    
    // Check if config button held (WiFi AP mode)
    delay(100);
    if (digitalRead(CONFIG_BUTTON) == LOW) {
        Serial.println("[CONFIG] Button held - entering configuration mode");
        enterConfigMode();
        return;  // Stay in config mode
    }
    
    // Initialize Ethernet
    Serial.println("[INIT] Starting Ethernet...");
    if (!initEthernet()) {
        Serial.println("[ERROR] Ethernet initialization failed!");
        // Fall back to WiFi?
        errorBlink();
    }
    
    // Connect to receiver
    connectToReceiver();
    
    Serial.println("[READY] Setup complete - waiting for paddle input");
    Serial.printf("[INFO] Mode: %s, WPM: %d, Dit: %dms\n", 
                  getModeName(), wpm, ditDuration);
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
    // Read paddle inputs (active-low)
    ditPaddle = !digitalRead(DIT_PIN);
    dahPaddle = !digitalRead(DAH_PIN);
    
    // Update keyer state machine
    updateKeyer();
    
    // Update status LED
    updateStatusLED();
    
    // Check TCP connection
    if (!tcpClient.connected()) {
        if (connected) {
            Serial.println("[TCP] Connection lost - reconnecting...");
            connected = false;
        }
        connectToReceiver();
        delay(1000);  // Retry delay
    }
    
    // Small delay for polling rate (1ms)
    delay(1);
}

// ============================================================================
// KEYER STATE MACHINE
// ============================================================================

void updateKeyer() {
    unsigned long now = millis();
    
    switch (keyerMode) {
        case STRAIGHT_KEY:
            updateStraightKey();
            break;
            
        case IAMBIC_A:
        case IAMBIC_B:
            updateIambicKeyer(now);
            break;
            
        case BUG:
            updateBugMode();
            break;
    }
}

void updateStraightKey() {
    // Simple: Dit paddle = key state
    bool keyState = ditPaddle;
    
    if (keyState != lastKeyState) {
        unsigned long now = millis();
        unsigned long duration = now - lastEventTime;
        
        sendCWEvent(keyState, duration);
        
        lastKeyState = keyState;
        lastEventTime = now;
    }
}

void updateIambicKeyer(unsigned long now) {
    static unsigned long elementStartTime = 0;
    static bool elementComplete = false;
    
    switch (keyerState) {
        case IDLE:
            // Sample paddles
            if (ditPaddle) {
                startElement(DIT, now);
            } else if (dahPaddle) {
                startElement(DAH, now);
            }
            break;
            
        case DIT:
        case DAH:
            // Check if element duration complete
            unsigned long elementDur = (keyerState == DIT) ? ditDuration : dahDuration;
            if (now - elementStartTime >= elementDur) {
                // Element finished
                endElement(now);
                
                // Check for opposite paddle (alternation)
                if (keyerState == DIT && (dahPaddle || dahMemory)) {
                    dahMemory = false;
                    startElement(DAH, now);
                } else if (keyerState == DAH && (ditPaddle || ditMemory)) {
                    ditMemory = false;
                    startElement(DIT, now);
                } else {
                    // Return to idle
                    keyerState = IDLE;
                }
            } else {
                // Mid-element: Sample paddles for memory (Mode B only)
                if (keyerMode == IAMBIC_B) {
                    if (keyerState == DIT && dahPaddle) {
                        dahMemory = true;
                    }
                    if (keyerState == DAH && ditPaddle) {
                        ditMemory = true;
                    }
                }
            }
            break;
    }
}

void startElement(KeyerState newState, unsigned long now) {
    keyerState = newState;
    
    // Send key DOWN event
    unsigned long duration = now - lastEventTime;
    sendCWEvent(true, duration);
    
    lastKeyState = true;
    lastEventTime = now;
}

void endElement(unsigned long now) {
    // Send key UP event
    unsigned long duration = now - lastEventTime;
    sendCWEvent(false, duration);
    
    lastKeyState = false;
    lastEventTime = now;
}

void updateBugMode() {
    // Bug mode: Automatic dits, manual dahs
    // TODO: Implement bug mode logic
}

// ============================================================================
// PROTOCOL: TCP-TS PACKET ENCODING
// ============================================================================

void sendCWEvent(bool keyDown, unsigned long durationMs) {
    if (!tcpClient.connected()) {
        return;  // No connection, drop packet
    }
    
    // Initialize transmission timeline on first packet
    if (transmissionStart == 0) {
        transmissionStart = millis();
        Serial.println("[TX] Transmission started");
    }
    
    // Calculate timestamp (ms since transmission start)
    uint32_t timestampMs = millis() - transmissionStart;
    
    // Build TCP-TS packet
    // Format: [length(2)] [seq(1)] [state(1)] [duration(1-2)] [timestamp(4)]
    
    uint8_t packet[16];  // Max size
    int packetLen = 0;
    
    // Sequence number
    packet[packetLen++] = sequenceNumber++;
    
    // Key state (0x00 = UP, 0x01 = DOWN)
    packet[packetLen++] = keyDown ? 0x01 : 0x00;
    
    // Duration (1 byte if <256ms, else 2 bytes big-endian)
    if (durationMs < 256) {
        packet[packetLen++] = (uint8_t)durationMs;
    } else {
        packet[packetLen++] = (durationMs >> 8) & 0xFF;  // MSB
        packet[packetLen++] = durationMs & 0xFF;         // LSB
    }
    
    // Timestamp (4 bytes, big-endian)
    packet[packetLen++] = (timestampMs >> 24) & 0xFF;
    packet[packetLen++] = (timestampMs >> 16) & 0xFF;
    packet[packetLen++] = (timestampMs >> 8) & 0xFF;
    packet[packetLen++] = timestampMs & 0xFF;
    
    // Add length prefix (2 bytes, big-endian)
    uint8_t framedPacket[18];
    framedPacket[0] = (packetLen >> 8) & 0xFF;  // Length MSB
    framedPacket[1] = packetLen & 0xFF;         // Length LSB
    memcpy(framedPacket + 2, packet, packetLen);
    
    // Send via TCP
    int totalLen = packetLen + 2;
    tcpClient.write(framedPacket, totalLen);
    
    // Update sidetone
    setSidetone(keyDown);
    
    // Debug output
    Serial.printf("[TX] %s duration=%lums timestamp=%ums seq=%d\n",
                  keyDown ? "DOWN" : "UP", durationMs, timestampMs, sequenceNumber - 1);
}

void setSidetone(bool keyDown) {
    if (sidetoneEnabled) {
        if (keyDown) {
            ledcWrite(SIDETONE_CHANNEL, 128);  // 50% duty cycle = tone ON
        } else {
            ledcWrite(SIDETONE_CHANNEL, 0);    // Silence
        }
    }
}

// ============================================================================
// NETWORK INITIALIZATION
// ============================================================================

bool initEthernet() {
    // Initialize Ethernet with LAN8720 PHY
    ETH.begin();
    
    // Wait for link (timeout after 10 seconds)
    int timeout = 100;  // 100 * 100ms = 10s
    while (!ETH.linkUp() && timeout > 0) {
        delay(100);
        timeout--;
    }
    
    if (!ETH.linkUp()) {
        Serial.println("[ETH] No link detected");
        return false;
    }
    
    Serial.println("[ETH] Link UP");
    Serial.printf("[ETH] MAC: %s\n", ETH.macAddress().c_str());
    
    // Wait for IP address (DHCP)
    timeout = 100;
    while (ETH.localIP() == IPAddress(0, 0, 0, 0) && timeout > 0) {
        delay(100);
        timeout--;
    }
    
    if (ETH.localIP() == IPAddress(0, 0, 0, 0)) {
        Serial.println("[ETH] Failed to get IP address");
        return false;
    }
    
    Serial.printf("[ETH] IP: %s\n", ETH.localIP().toString().c_str());
    Serial.printf("[ETH] Gateway: %s\n", ETH.gatewayIP().toString().c_str());
    
    return true;
}

void connectToReceiver() {
    if (tcpClient.connected()) {
        return;  // Already connected
    }
    
    Serial.printf("[TCP] Connecting to %s:%d...\n", 
                  receiverIP.toString().c_str(), receiverPort);
    
    digitalWrite(STATUS_LED, LOW);  // LED off during connection
    
    if (tcpClient.connect(receiverIP, receiverPort, TCP_TIMEOUT_MS)) {
        connected = true;
        transmissionStart = 0;  // Reset timeline
        sequenceNumber = 0;
        
        Serial.println("[TCP] Connected!");
        digitalWrite(STATUS_LED, HIGH);
    } else {
        connected = false;
        Serial.println("[TCP] Connection failed");
    }
}

// ============================================================================
// CONFIGURATION
// ============================================================================

void loadConfiguration() {
    prefs.begin("cw-keyer", false);
    
    // Load receiver IP (stored as string)
    String ipStr = prefs.getString("receiver_ip", DEFAULT_RECEIVER_IP);
    receiverIP.fromString(ipStr);
    
    // Load receiver port
    receiverPort = prefs.getUInt("receiver_port", DEFAULT_RECEIVER_PORT);
    
    // Load WPM
    wpm = prefs.getInt("wpm", DEFAULT_WPM);
    
    // Load keyer mode
    int mode = prefs.getInt("keyer_mode", IAMBIC_B);
    keyerMode = (KeyerMode)mode;
    
    // Load sidetone enable
    sidetoneEnabled = prefs.getBool("sidetone", true);
    
    prefs.end();
    
    Serial.println("[CONFIG] Loaded from EEPROM:");
    Serial.printf("  Receiver: %s:%d\n", receiverIP.toString().c_str(), receiverPort);
    Serial.printf("  WPM: %d\n", wpm);
    Serial.printf("  Mode: %s\n", getModeName());
    Serial.printf("  Sidetone: %s\n", sidetoneEnabled ? "ON" : "OFF");
}

void saveConfiguration() {
    prefs.begin("cw-keyer", false);
    
    prefs.putString("receiver_ip", receiverIP.toString());
    prefs.putUInt("receiver_port", receiverPort);
    prefs.putInt("wpm", wpm);
    prefs.putInt("keyer_mode", keyerMode);
    prefs.putBool("sidetone", sidetoneEnabled);
    
    prefs.end();
    
    Serial.println("[CONFIG] Saved to EEPROM");
}

void enterConfigMode() {
    // TODO: Implement WiFi AP + web UI for configuration
    Serial.println("[CONFIG] Configuration mode not yet implemented");
    Serial.println("[CONFIG] Use serial console to configure");
    
    // For now, just blink LED and wait for reset
    while (true) {
        digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
        delay(200);
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

void calculateTimings() {
    ditDuration = DIT_DURATION(wpm);
    dahDuration = ditDuration * 3;
    
    Serial.printf("[TIMING] WPM: %d, Dit: %dms, Dah: %dms\n", 
                  wpm, ditDuration, dahDuration);
}

const char* getModeName() {
    switch (keyerMode) {
        case STRAIGHT_KEY: return "Straight Key";
        case IAMBIC_A: return "Iambic A";
        case IAMBIC_B: return "Iambic B";
        case BUG: return "Bug";
        default: return "Unknown";
    }
}

void updateStatusLED() {
    static unsigned long lastBlink = 0;
    unsigned long now = millis();
    
    if (connected) {
        // Solid ON when connected
        digitalWrite(STATUS_LED, HIGH);
    } else {
        // Slow blink when not connected
        if (now - lastBlink > 500) {
            digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
            lastBlink = now;
        }
    }
}

void errorBlink() {
    // Fast blink for error condition
    while (true) {
        digitalWrite(STATUS_LED, HIGH);
        delay(100);
        digitalWrite(STATUS_LED, LOW);
        delay(100);
    }
}
