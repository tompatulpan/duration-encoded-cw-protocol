/*
 * XIAO SAMD21 USB HID CW Key Interface
 *
 * Reads paddle inputs and sends USB keyboard events (Ctrl keys).
 * Based on Vail-CW adapter design - uses Arduino Keyboard library.
 *
 * Hardware: Seeed Studio XIAO SAMD21
 * Protocol: USB HID Keyboard (Left Ctrl = Dit, Right Ctrl = Dah)
 * Receiver: Python script reads HID → sends TCP-TS packets
 *
 * Pin assignments:
 *   D2 (PA08) - Dit paddle input (internal pull-up, active-low)
 *   D1 (PA04) - Dah paddle input (internal pull-up, active-low)
 *   D0 (PA02) - Unused (future: mode button)
 *   LED_BUILTIN - Status LED (blinks on paddle press)
 *
 * USB VID:PID: 0x2886:0x802F (Seeed XIAO SAMD21)
 * Reference: Vail-CW/vail-adapter (MIT License)
 */

#include <Keyboard.h>

// Pin definitions (matching Vail design)
const int DIT_PIN = 2;      // D2 (PA08)
const int DAH_PIN = 1;      // D1 (PA04)

// Keyboard keys to send
#define DIT_KEY KEY_LEFT_CTRL
#define DAH_KEY KEY_RIGHT_CTRL

// Polling rate
const int POLL_INTERVAL_MS = 1;

// Debounce time (microseconds)
const int DEBOUNCE_US = 500;

bool ditPressed = false;
bool dahPressed = false;

unsigned long lastDitChange = 0;
unsigned long lastDahChange = 0;
unsigned long pressCount = 0;

// Debug counters
unsigned long loopCount = 0;
unsigned long lastDebugPrint = 0;

void setup() {
    // Start serial FIRST for debugging
    Serial.begin(115200);
    
    pinMode(DIT_PIN, INPUT_PULLUP);
    pinMode(DAH_PIN, INPUT_PULLUP);
    pinMode(LED_BUILTIN, OUTPUT);

    // Wait for serial connection (timeout after 2 seconds)
    unsigned long serialStart = millis();
    while (!Serial && (millis() - serialStart < 2000)) {
        delay(10);
    }

    Serial.println();
    Serial.println("===========================================");
    Serial.println("XIAO SAMD21 USB HID CW Key - Keyboard Mode");
    Serial.println("===========================================");
    Serial.println("Hardware Setup:");
    Serial.println("  Dit paddle:  D2 (PA08) - active-low");
    Serial.println("  Dah paddle:  D1 (PA04) - active-low");
    Serial.println();
    Serial.print("Pin states at startup: ");
    Serial.print("D2="); Serial.print(digitalRead(DIT_PIN));
    Serial.print(" D1="); Serial.println(digitalRead(DAH_PIN));
    Serial.println();

    // Initialize USB Keyboard (Arduino built-in)
    Serial.println("Initializing USB Keyboard...");
    Keyboard.begin();
    Serial.println("USB Keyboard initialized!");
    Serial.println("Sending: Left Ctrl (Dit), Right Ctrl (Dah)");
    Serial.println();

    // Startup blink sequence
    Serial.println("Startup blink sequence...");
    for (int i = 0; i < 3; i++) {
        digitalWrite(LED_BUILTIN, HIGH);
        delay(100);
        digitalWrite(LED_BUILTIN, LOW);
        delay(100);
    }
    
    Serial.println("===========================================");
    Serial.println("Setup complete - entering main loop");
    Serial.println("Debug output every 1000 loops (~1 second)");
    Serial.println("Button presses shown immediately");
    Serial.println("===========================================");
    Serial.println();
}

void loop() {
    loopCount++;
    
    // Read paddles (active-low)
    bool ditNow = !digitalRead(DIT_PIN);
    bool dahNow = !digitalRead(DAH_PIN);

    // Debounce
    unsigned long now = micros();
    if (ditNow != ditPressed && (now - lastDitChange) > DEBOUNCE_US) {
        ditPressed = ditNow;
        lastDitChange = now;
        if (ditPressed) {
            pressCount++;
            Keyboard.press(DIT_KEY);
            Serial.print("[EVENT] Dit pressed (count=");
            Serial.print(pressCount);
            Serial.print(", loop=");
            Serial.print(loopCount);
            Serial.println(") - Sending Left Ctrl");
        } else {
            Keyboard.release(DIT_KEY);
            Serial.println("[EVENT] Dit released - Releasing Left Ctrl");
        }
    }

    if (dahNow != dahPressed && (now - lastDahChange) > DEBOUNCE_US) {
        dahPressed = dahNow;
        lastDahChange = now;
        if (dahPressed) {
            pressCount++;
            Keyboard.press(DAH_KEY);
            Serial.print("[EVENT] Dah pressed (count=");
            Serial.print(pressCount);
            Serial.print(", loop=");
            Serial.print(loopCount);
            Serial.println(") - Sending Right Ctrl");
        } else {
            Keyboard.release(DAH_KEY);
            Serial.println("[EVENT] Dah released - Releasing Right Ctrl");
        }
    }

    // LED indicator
    digitalWrite(LED_BUILTIN, (ditPressed || dahPressed) ? HIGH : LOW);

    // Periodic heartbeat (every 1000 loops = ~1 second)
    if (loopCount % 1000 == 0) {
        unsigned long now_ms = millis();
        Serial.print("[HEARTBEAT] Loop: ");
        Serial.print(loopCount);
        Serial.print(", Time: ");
        Serial.print(now_ms);
        Serial.print("ms, Presses: ");
        Serial.print(pressCount);
        Serial.print(", Current state: dit=");
        Serial.print(ditPressed ? "1" : "0");
        Serial.print(", dah=");
        Serial.println(dahPressed ? "1" : "0");
        lastDebugPrint = now_ms;
    }

    delay(POLL_INTERVAL_MS);
}
