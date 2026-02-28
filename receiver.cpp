/*
  Spray Bot - Receiver 1 (pcb1)
  Change DEVICE_ID only for pcb2 and pcb3 — everything else identical
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
const char* DEVICE_ID     = "pcb1";   // ← Change to "pcb2" or "pcb3" for other receivers

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

// ============ RELAY PINS ============
const int RELAY_PINS[DIR_COUNT] = { 2, 3, 4, 5, 6, 7 };
// NOTE: Active-low relay module — HIGH = OFF, LOW = ON

// ============ CONFLICT PAIRS ============
const int CONFLICT_PAIRS[3][2] = {
  { D_BASE_LEFT,  D_BASE_RIGHT },
  { D_LP_UP,      D_LP_DOWN    },
  { D_RP_UP,      D_RP_DOWN    }
};

WebSocketsClient wsClient;
bool wsConnected = false;

unsigned long lastWifiCheck = 0;
#define WIFI_CHECK_INTERVAL 10000

// ============ RELAY CONTROL ============
void stopAll() {
  for (int i = 0; i < DIR_COUNT; i++)
    digitalWrite(RELAY_PINS[i], HIGH);
  Serial.println("  All relays OFF");
}

void handleCommand(int d, int s) {
  if (d < 0 || d >= DIR_COUNT) return;

  if (s == 1) {
    for (int i = 0; i < 3; i++) {
      if (CONFLICT_PAIRS[i][0] == d || CONFLICT_PAIRS[i][1] == d) {
        int other = (CONFLICT_PAIRS[i][0] == d) ? CONFLICT_PAIRS[i][1] : CONFLICT_PAIRS[i][0];
        if (digitalRead(RELAY_PINS[other]) == LOW) {
          digitalWrite(RELAY_PINS[other], HIGH);
          Serial.print("  X Cleared: "); Serial.println(DIR_NAMES[other]);
        }
        break;
      }
    }
    digitalWrite(RELAY_PINS[d], LOW);
    Serial.print("  > "); Serial.print(DIR_NAMES[d]); Serial.println(" ON");
  } else {
    digitalWrite(RELAY_PINS[d], HIGH);
    Serial.print("  | "); Serial.print(DIR_NAMES[d]); Serial.println(" OFF");
  }
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
        doc["clientType"] = "pcb";
        doc["deviceId"]   = DEVICE_ID;
        String msg;
        serializeJson(doc, msg);
        wsClient.sendTXT(msg);
        Serial.print("Registered as ["); Serial.print(DEVICE_ID); Serial.println("]");
      }
      break;

    case WStype_DISCONNECTED:
      Serial.println("WS: Disconnected");
      wsConnected = false;
      stopAll();
      break;

    case WStype_TEXT:
      {
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, payload, length);
        if (!err && doc["d"].is<int>()) {
          int d = doc["d"];
          int s = doc["s"];
          Serial.print("[CMD] d="); Serial.print(d);
          Serial.print(" s="); Serial.println(s);
          handleCommand(d, s);
        }
      }
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
    delay(500); Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("WiFi! IP: "); Serial.println(WiFi.localIP());
    return true;
  }
  Serial.println("\nWiFi failed.");
  return false;
}

void checkWifi() {
  if (millis() - lastWifiCheck < WIFI_CHECK_INTERVAL) return;
  lastWifiCheck = millis();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost! Reconnecting...");
    wsConnected = false;
    stopAll();
    WiFi.disconnect();
    delay(1000);
    connectWifi();
  }
}

// ============ SETUP ============
void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println("========================================");
  Serial.print("  Spray Bot - Receiver ["); Serial.print(DEVICE_ID); Serial.println("]");
  Serial.println("========================================\n");

  for (int i = 0; i < DIR_COUNT; i++) {
    digitalWrite(RELAY_PINS[i], HIGH);  // relays OFF before setting as output
    pinMode(RELAY_PINS[i], OUTPUT);
  }

  if (!connectWifi()) {
    while (true) delay(1000);
  }

  wsClient.beginSSL(WS_HOST, WS_PORT, WS_PATH, (uint8_t*)NULL);
  wsClient.onEvent(webSocketEvent);
  wsClient.setReconnectInterval(5000);
  wsClient.enableHeartbeat(25000, 5000, 3);

  Serial.println("Connecting to WebSocket...");
}

// ============ LOOP ============
void loop() {
  checkWifi();
  wsClient.loop();
}
