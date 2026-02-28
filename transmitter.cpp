/*
  Spray Bot - Transmitter
  Raspberry Pi Pico W - Arduino IDE

  3 selector buttons decide which receiver(s) get the commands:
    BTN1 alone  → pcb1
    BTN2 alone  → pcb2
    BTN3 alone  → pcb3
    BTN1+BTN2   → pcb1 + pcb2
    BTN1+BTN3   → pcb1 + pcb3
    BTN2+BTN3   → pcb2 + pcb3
    BTN1+2+3    → pcb1 + pcb2 + pcb3
    none        → no command sent

  Required Libraries:
    - WebSockets by Markus Sattler
    - ArduinoJson by Benoit Blanchon (v7+)
*/

#include <Arduino.h>
#include <WiFi.h>
#include <WebSockets.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ============ CONFIGURATION ============
const char* WIFI_SSID     = "test";
const char* WIFI_PASSWORD = "12345678";
const char* WS_HOST       = "holy-backend-64n1.onrender.com";
const int   WS_PORT       = 443;
const char* WS_PATH       = "/";
const char* DEVICE_ID     = "controller1";

// Receiver device IDs
const char* RECEIVERS[3]  = { "pcb1", "pcb2", "pcb3" };

// ============ DIRECTION CODES ============
#define D_BASE_LEFT  0
#define D_BASE_RIGHT 1
#define D_LP_UP      2
#define D_LP_DOWN    3
#define D_RP_UP      4
#define D_RP_DOWN    5
#define DIR_COUNT    6

const char* DIR_NAMES[DIR_COUNT] = {
  "BASE_L", "BASE_R", "LP_UP", "LP_DN", "RP_UP", "RP_DN"
};

// ============ JOYSTICK PINS ============
#define JS1_UP_PIN    2
#define JS1_DOWN_PIN  3
#define JS1_LEFT_PIN  4
#define JS1_RIGHT_PIN 5
#define JS2_UP_PIN    6
#define JS2_DOWN_PIN  7
#define JS2_LEFT_PIN  8
#define JS2_RIGHT_PIN 9

// ============ SELECTOR BUTTON PINS ============
// Active LOW — connect each button between pin and GND
#define BTN1_PIN  10   // selects pcb1
#define BTN2_PIN  11   // selects pcb2
#define BTN3_PIN  12   // selects pcb3

// ============ STATE TRACKING ============
bool last_state[DIR_COUNT]    = { false };
bool last_btn[3]              = { false };
bool wsConnected              = false;

// ============ WEBSOCKET CLIENT ============
WebSocketsClient wsClient;

// ============ READ SELECTOR BUTTONS ============
// Returns bitmask: bit0=btn1, bit1=btn2, bit2=btn3
uint8_t readSelectorButtons() {
  uint8_t mask = 0;
  if (!digitalRead(BTN1_PIN)) mask |= 0x01;  // active LOW
  if (!digitalRead(BTN2_PIN)) mask |= 0x02;
  if (!digitalRead(BTN3_PIN)) mask |= 0x04;
  return mask;
}

// ============ SEND COMMAND ============
// Sends command to all selected receivers
void sendCmd(int d, bool active, uint8_t selectorMask) {
  if (selectorMask == 0) return;  // no receiver selected — don't send

  for (int i = 0; i < 3; i++) {
    if (selectorMask & (1 << i)) {
      JsonDocument doc;
      doc["type"] = "command";
      doc["d"]    = d;
      doc["s"]    = active ? 1 : 0;
      doc["t"]    = RECEIVERS[i];

      String msg;
      serializeJson(doc, msg);
      wsClient.sendTXT(msg);
    }
  }

  // Print targets for debugging
  Serial.print(active ? "  > " : "  | ");
  Serial.print(DIR_NAMES[d]);
  Serial.print(" → ");
  for (int i = 0; i < 3; i++) {
    if (selectorMask & (1 << i)) {
      Serial.print(RECEIVERS[i]);
      Serial.print(" ");
    }
  }
  Serial.println();
}

// ============ WEBSOCKET EVENT ============
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.println("WS: Connected");
      wsConnected = true;
      {
        JsonDocument doc;
        doc["type"]       = "register";
        doc["clientType"] = "controller";
        doc["deviceId"]   = DEVICE_ID;
        String msg;
        serializeJson(doc, msg);
        wsClient.sendTXT(msg);
        Serial.print("Registered as [");
        Serial.print(DEVICE_ID);
        Serial.println("]\nController ready!\n");
      }
      break;

    case WStype_DISCONNECTED:
      Serial.println("WS: Disconnected");
      wsConnected = false;
      memset(last_state, 0, sizeof(last_state));
      break;

    case WStype_ERROR:
      Serial.println("WS: Error");
      break;

    default: break;
  }
}

// ============ WIFI ============
bool connectWifi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int timeout = 20;
  while (WiFi.status() != WL_CONNECTED && timeout-- > 0) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("WiFi connected! IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }
  Serial.println("\nWiFi failed.");
  return false;
}

// ============ READ JOYSTICKS ============
void readActions(bool* out) {
  bool js1_up    = !digitalRead(JS1_UP_PIN);
  bool js1_down  = !digitalRead(JS1_DOWN_PIN);
  bool js1_left  = !digitalRead(JS1_LEFT_PIN);
  bool js1_right = !digitalRead(JS1_RIGHT_PIN);
  bool js2_up    = !digitalRead(JS2_UP_PIN);
  bool js2_down  = !digitalRead(JS2_DOWN_PIN);
  bool js2_left  = !digitalRead(JS2_LEFT_PIN);
  bool js2_right = !digitalRead(JS2_RIGHT_PIN);

  bool raw_left  = js1_left  || js2_left;
  bool raw_right = js1_right || js2_right;
  bool base_left, base_right;

  if (raw_left && raw_right) {
    base_left  = js1_left  && !js1_right;
    base_right = js1_right && !js1_left;
    if (!base_left && !base_right) {
      base_left  = js2_left  && !js2_right;
      base_right = js2_right && !js2_left;
    }
  } else {
    base_left  = raw_left;
    base_right = raw_right;
  }

  out[D_BASE_LEFT]  = base_left;
  out[D_BASE_RIGHT] = base_right;
  out[D_LP_UP]      = js1_up;
  out[D_LP_DOWN]    = js1_down;
  out[D_RP_UP]      = js2_up;
  out[D_RP_DOWN]    = js2_down;
}

// ============ SETUP ============
void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println("========================================");
  Serial.println("  Spray Bot - Transmitter");
  Serial.println("========================================\n");

  // Joystick pins
  int jsPins[] = {
    JS1_UP_PIN, JS1_DOWN_PIN, JS1_LEFT_PIN, JS1_RIGHT_PIN,
    JS2_UP_PIN, JS2_DOWN_PIN, JS2_LEFT_PIN, JS2_RIGHT_PIN
  };
  for (int i = 0; i < 8; i++) pinMode(jsPins[i], INPUT_PULLUP);

  // Selector button pins
  pinMode(BTN1_PIN, INPUT_PULLUP);
  pinMode(BTN2_PIN, INPUT_PULLUP);
  pinMode(BTN3_PIN, INPUT_PULLUP);

  if (!connectWifi()) {
    Serial.println("Halting - WiFi failed.");
    while (true) delay(1000);
  }

  wsClient.beginSSL(WS_HOST, WS_PORT, WS_PATH);
  wsClient.onEvent(webSocketEvent);
  wsClient.setReconnectInterval(5000);
  wsClient.enableHeartbeat(25000, 5000, 3);

  Serial.println("Connecting to WebSocket...");
}

// ============ LOOP ============
void loop() {
  wsClient.loop();
  if (!wsConnected) return;

  // Read which receivers are selected
  uint8_t selectorMask = readSelectorButtons();

  // Read joystick actions
  bool current[DIR_COUNT];
  readActions(current);

  // Send on state change
  for (int d = 0; d < DIR_COUNT; d++) {
    if (current[d] != last_state[d]) {
      sendCmd(d, current[d], selectorMask);
      last_state[d] = current[d];
    }
  }

  delay(20);
}
