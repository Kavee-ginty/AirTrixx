#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <ctype.h>
#include <string.h>
#include <math.h>

#if __has_include("../shared/AirTrixxConfig.h")
#include "../shared/AirTrixxConfig.h"
#include "../shared/AirTrixxProtocol.h"
#else
#include "AirTrixxConfig.h"
#include "AirTrixxProtocol.h"
#endif

// ============================================================
// CONFIG
// ============================================================
#define NUM_SENSORS            4
#define TCA_ADDR               0x70
#define AVG_WINDOW             7
#define MIN_AVG_READY          4
#define CALIBRATION_SAMPLES    25
#define IDLE_CALIBRATION_WAIT_MS 3000
#define DEFAULT_MAX_SIGNAL_DISTANCE_MM 360
#define COVER_CALIBRATION_WAIT_MS 3000
#define COVER_LIMIT_MARGIN_MM 5
#define MEASUREMENT_BUDGET_US  20000
#define TCA_SETTLE_US          700
#define SENSOR_INIT_RETRIES    3
#define LOG_SAMPLE_INTERVAL_MS 20
#define LOG_LABEL_MAX_LEN      32

#if defined(CONFIG_IDF_TARGET_ESP32S3) || defined(ARDUINO_ESP32S3_DEV)
  #define I2C_SDA_PIN 8
  #define I2C_SCL_PIN 9
#elif defined(ESP32)
  #define I2C_SDA_PIN 21
  #define I2C_SCL_PIN 22
#else
  #define I2C_SDA_PIN 8
  #define I2C_SCL_PIN 9
#endif

// ============================================================
// GLOBALS
// ============================================================
#define NUM_KEY_MAPS 4
Adafruit_VL53L0X lox[NUM_SENSORS];
bool loxReady[NUM_SENSORS] = {false, false, false, false};

int   zeroMM[NUM_SENSORS]     = {0, 0, 0, 0};
int   idleMM[NUM_SENSORS]     = {9999, 9999, 9999, 9999};
bool  idleValid[NUM_SENSORS]  = {false, false, false, false};
int   maxSignalMM[NUM_SENSORS] = {
  DEFAULT_MAX_SIGNAL_DISTANCE_MM,
  DEFAULT_MAX_SIGNAL_DISTANCE_MM,
  DEFAULT_MAX_SIGNAL_DISTANCE_MM,
  DEFAULT_MAX_SIGNAL_DISTANCE_MM
};

int     avgBuffer[NUM_SENSORS][AVG_WINDOW] = {};
long    avgSum[NUM_SENSORS]   = {0, 0, 0, 0};
uint8_t avgPos[NUM_SENSORS]   = {0, 0, 0, 0};
uint8_t avgCount[NUM_SENSORS] = {0, 0, 0, 0};

bool  loggingMode         = false;
char  logLabel[LOG_LABEL_MAX_LEN] = "";
bool  logHeaderPrinted    = false;
unsigned long lastLogMs   = 0;
unsigned long logFrame    = 0;
uint16_t airTrixxKeyboardSequence = 0;
uint16_t airTrixxKeyboardBatterySequence = 0;
unsigned long lastAirTrixxReportMs = 0;
unsigned long lastAirTrixxBatteryReportMs = 0;
bool airTrixxBatteryReportSent = false;
volatile bool airTrixxRecalibrationRequested = false;
bool airTrixxWirelessReady = false;
volatile bool airTrixxStartupBeaconActive = false;
volatile int startupRawMM[NUM_SENSORS] = {-1, -1, -1, -1};
volatile bool startupRawValid[NUM_SENSORS] = {false, false, false, false};

// Exact horizontal key ranges measured from sensors on the right side.
// Distance starts at P/L/M/Return and increases toward the left side.
const uint16_t TOP_STARTS[]  = { 60,  86, 112, 138, 164, 190, 216, 242, 268, 294};
const uint16_t TOP_ENDS[]    = { 86, 112, 138, 164, 190, 216, 242, 268, 294, 320};
const uint16_t HOME_STARTS[] = { 50,  79, 108, 137, 166, 195, 224, 253, 282};
const uint16_t HOME_ENDS[]   = { 79, 108, 137, 166, 195, 224, 253, 282, 310};
const uint16_t LOWER_STARTS[] = {  0, 100, 123, 146, 169, 192, 215, 238, 261};
const uint16_t LOWER_ENDS[]   = { 99, 123, 146, 169, 192, 215, 238, 260, 320};
const uint16_t CTRL_STARTS[]  = {  0,  70, 251};
const uint16_t CTRL_ENDS[]    = { 69, 250, 320};

// Special actions: ^ = Shift, < = Backspace, # = ?123, space = Space, \r = Return.
struct ChannelMap {
  uint8_t ch;
  const char *actions;
  const char *labels;
  const uint16_t *starts;
  const uint16_t *ends;
  uint8_t count;
};
ChannelMap keyMaps[] = {
  {1, "poiuytrewq", "P O I U Y T R E W Q", TOP_STARTS, TOP_ENDS, 10},
  {2, "lkjhgfdsa",  "L K J H G F D S A", HOME_STARTS, HOME_ENDS, 9},
  {0, "<mnbvcxz^",  "BACKSPACE M N B V C X Z SHIFT", LOWER_STARTS, LOWER_ENDS, 9},
  {3, "\r #",       "RETURN SPACE ?123", CTRL_STARTS, CTRL_ENDS, 3}
};

void printChannelMappings();
void printDetectionLimits();
void sendAirTrixxKeyboardTof(int rawMM[], bool rawValid[]);
void sendAirTrixxKeyboardBattery(bool force = false);

// ============================================================
// SENSOR HELPERS
// ============================================================
uint8_t chToIdx(uint8_t ch) {
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) if (keyMaps[i].ch == ch) return i;
  return 255;
}

void tcaSelect(uint8_t channel) {
  Wire.beginTransmission(TCA_ADDR);
  Wire.write(1 << channel);
  Wire.endTransmission();
  delayMicroseconds(TCA_SETTLE_US);
}

bool readRaw(uint8_t ch, int &distanceMM) {
  VL53L0X_RangingMeasurementData_t measure;
  tcaSelect(ch);
  uint8_t idx = chToIdx(ch);
  if (idx == 255) return false;
  if (!loxReady[idx]) return false;
  lox[idx].rangingTest(&measure, false);
  if (measure.RangeStatus == 4 || measure.RangeMilliMeter <= 0 || measure.RangeMilliMeter >= 8190) return false;
  distanceMM = measure.RangeMilliMeter;
  return true;
}

void sortValues(int v[], int n) {
  for (int i = 1; i < n; i++) {
    int key = v[i], j = i-1;
    while (j >= 0 && v[j] > key) { v[j+1] = v[j]; j--; }
    v[j+1] = key;
  }
}

bool readTrimmedAverage(uint8_t ch, int &avgMM, int samples, int &valid) {
  int values[CALIBRATION_SAMPLES];
  valid = 0;
  for (int i = 0; i < samples; i++) {
    int d;
    bool readingValid = readRaw(ch, d);
    if (readingValid) values[valid++] = d;
    for (uint8_t sensor = 0; sensor < NUM_KEY_MAPS; sensor++) {
      if (keyMaps[sensor].ch == ch) {
        startupRawMM[sensor] = readingValid ? d : -1;
        startupRawValid[sensor] = readingValid;
        break;
      }
    }
    delay(2);
  }
  if (valid < (samples/2 + 1)) return false;
  sortValues(values, valid);
  int start = valid >= 5 ? 1 : 0, end = valid >= 5 ? valid-1 : valid;
  long total = 0;
  for (int i = start; i < end; i++) total += values[i];
  avgMM = total / (end - start);
  return true;
}

void resetMovingAverages() {
  for (uint8_t i = 0; i < NUM_SENSORS; i++) { avgSum[i] = 0; avgPos[i] = 0; avgCount[i] = 0; }
}

void addMovingSample(uint8_t ch, int mm) {
  uint8_t i = chToIdx(ch); if (i == 255) return;
  if (avgCount[i] < AVG_WINDOW) { avgBuffer[i][avgPos[i]] = mm; avgSum[i] += mm; avgCount[i]++; }
  else { avgSum[i] -= avgBuffer[i][avgPos[i]]; avgBuffer[i][avgPos[i]] = mm; avgSum[i] += mm; }
  avgPos[i] = (avgPos[i] + 1) % AVG_WINDOW;
}

bool getMovingAverage(uint8_t ch, int &avgMM) {
  uint8_t i = chToIdx(ch); if (i == 255 || avgCount[i] < MIN_AVG_READY) return false;
  avgMM = avgSum[i] / avgCount[i]; return true;
}

// ============================================================
// LOGGING
// ============================================================
void printLogHeader() {
  Serial.print("frame,ms,label");
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) { Serial.print(",ch"); Serial.print(keyMaps[i].ch); Serial.print("_raw"); }
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) { Serial.print(",ch"); Serial.print(keyMaps[i].ch); Serial.print("_mm"); }
  Serial.println();
}

void printLogRow(int rawMM[], bool rawValid[], int relativeMM[]) {
  Serial.print(logFrame++); Serial.print(','); Serial.print(millis()); Serial.print(','); Serial.print(logLabel);
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) { Serial.print(','); if (rawValid[i]) Serial.print(rawMM[i]); else Serial.print(-1); }
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) { Serial.print(','); Serial.print(relativeMM[i]); }
  Serial.println();
}

// ============================================================
// SERIAL COMMANDS
// ============================================================
bool eqIC(const char *a, const char *b) {
  while (*a && *b) { if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return false; a++; b++; }
  return !*a && !*b;
}
bool swIC(const char *t, const char *p) {
  while (*p) { if (!*t || tolower((unsigned char)*t) != tolower((unsigned char)*p)) return false; t++; p++; }
  return true;
}

void handleSerialCommand() {
  static char line[64]; static uint8_t pos = 0;
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      line[pos] = '\0'; pos = 0;
      if (!line[0]) continue;
      if      (eqIC(line, "help"))    Serial.println("Commands: ai on | ai off | log on | log off | label <text> | clear | map");
      else if (eqIC(line, "map"))     printChannelMappings();
      else if (eqIC(line, "ai on"))   { loggingMode = true; logHeaderPrinted = false; lastLogMs = 0; Serial.println("AI RAW STREAM ON"); }
      else if (eqIC(line, "ai off"))  { loggingMode = false; Serial.println("AI RAW STREAM OFF"); }
      else if (eqIC(line, "log on"))  { loggingMode = true; logHeaderPrinted = false; lastLogMs = 0; Serial.println("LOGGING ON"); }
      else if (eqIC(line, "log off")) { loggingMode = false; Serial.println("LOGGING OFF"); }
      else if (eqIC(line, "clear"))   { logLabel[0] = '\0'; Serial.println("LABEL CLEARED"); }
      else if (swIC(line, "label "))  { strncpy(logLabel, line+6, LOG_LABEL_MAX_LEN-1); logLabel[LOG_LABEL_MAX_LEN-1] = '\0'; Serial.print("LABEL SET: "); Serial.println(logLabel); }
      else if (eqIC(line, "dist") || eqIC(line, "measure")) {
        // Print a single-shot distance reading for each channel (mm), -1 = invalid
        for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
          uint8_t ch = keyMaps[i].ch;
          int d = -1;
          tcaSelect(ch);
          if (readRaw(ch, d)) {
            Serial.print("CH"); Serial.print(ch); Serial.print("="); Serial.print(d);
          } else {
            Serial.print("CH"); Serial.print(ch); Serial.print("=-1");
          }
          if (i < NUM_KEY_MAPS - 1) Serial.print(", ");
        }
        Serial.println();
      }
      else if (eqIC(line, "limits")) {
        printDetectionLimits();
      }
      else                            Serial.println("Unknown command. Type: help");
    } else if (pos < sizeof(line)-1) line[pos++] = c;
  }
}

// ============================================================
// CALIBRATION
// ============================================================
void haltWithError(const char *msg) {
  Serial.print("FATAL ERROR: "); Serial.println(msg);
  while (1) {
    Serial.print("FATAL ERROR: "); Serial.println(msg);
    Serial.println("System halted. Reset to retry.");
    delay(3000);
  }
}

void printChannelMappings() {
  Serial.println("Channel key mappings:");
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
    Serial.print("  CH");
    Serial.print(keyMaps[i].ch);
    Serial.print(" -> ");
    Serial.println(keyMaps[i].labels);
    Serial.print("    accepted ranges: ");
    for (uint8_t j = 0; j < keyMaps[i].count; j++) {
      if (j > 0) Serial.print(" | ");
      int rangeStart = keyMaps[i].starts[j];
      int rangeEnd = keyMaps[i].ends[j];
      Serial.print(rangeStart);
      Serial.print('-');
      Serial.print(rangeEnd);
      Serial.print("mm");
    }
    Serial.println();
  }
}

void printDetectionLimits() {
  Serial.print("DETECT_LIMITS_MM");
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
    Serial.print(",ch");
    Serial.print(keyMaps[i].ch);
    Serial.print("=");
    Serial.print(maxSignalMM[i]);
  }
  Serial.println();
}

void calibrateDetectionLimits() {
  Serial.println("COVER DISTANCE CALIBRATION");
  Serial.println("Cover all sensors at the farthest distance you want detected.");
  Serial.print("Starting in ");
  Serial.print(COVER_CALIBRATION_WAIT_MS / 1000);
  Serial.println(" seconds...");
  unsigned long waitStartedMs = millis();
  while (millis() - waitStartedMs < COVER_CALIBRATION_WAIT_MS) {
    for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
      int rawMM = -1;
      startupRawValid[i] = readRaw(keyMaps[i].ch, rawMM);
      startupRawMM[i] = startupRawValid[i] ? rawMM : -1;
    }
    delay(2);
  }

  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
    uint8_t ch = keyMaps[i].ch;
    if (!loxReady[i]) {
      Serial.print("CH"); Serial.print(ch);
      Serial.println(" not ready, using default detect limit");
      continue;
    }
    int d;
    int validReadings = 0;
    if (readTrimmedAverage(ch, d, CALIBRATION_SAMPLES, validReadings)) {
      maxSignalMM[i] = max(DEFAULT_MAX_SIGNAL_DISTANCE_MM, d + COVER_LIMIT_MARGIN_MM);
      Serial.print("CH"); Serial.print(ch);
      Serial.print(" covered distance = "); Serial.print(d);
      Serial.print("mm, detect limit = "); Serial.print(maxSignalMM[i]);
      Serial.println("mm");
    } else {
      Serial.print("CH"); Serial.print(ch);
      Serial.print(" cover calibration failed with ");
      Serial.print(validReadings);
      Serial.print("/");
      Serial.print(CALIBRATION_SAMPLES);
      Serial.println(" valid readings, using default detect limit");
    }
  }
  printDetectionLimits();
}

void calibrateIdleBackground() {
  Serial.println("AUTOMATIC IDLE CALIBRATION");
  Serial.println("Remove hands and objects from the keyboard.");
  Serial.print("Starting in ");
  Serial.print(IDLE_CALIBRATION_WAIT_MS / 1000);
  Serial.println(" seconds...");
  unsigned long waitStartedMs = millis();
  while (millis() - waitStartedMs < IDLE_CALIBRATION_WAIT_MS) {
    for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
      int rawMM = -1;
      startupRawValid[i] = readRaw(keyMaps[i].ch, rawMM);
      startupRawMM[i] = startupRawValid[i] ? rawMM : -1;
    }
    delay(2);
  }

  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
    uint8_t ch = keyMaps[i].ch;
    if (!loxReady[i]) {
      Serial.print("CH"); Serial.print(ch);
      Serial.println(" not ready, skipping idle calibration");
      continue;
    }
    int d;
    int validReadings = 0;
    if (readTrimmedAverage(ch, d, CALIBRATION_SAMPLES, validReadings)) {
      idleMM[i] = d;
      zeroMM[i] = 0;
      idleValid[i] = true;
      Serial.print("CH"); Serial.print(ch);
      Serial.print(" idle/background = "); Serial.print(d);
      Serial.println("mm");
    } else {
      idleValid[i] = false;
      Serial.print("CH"); Serial.print(ch);
      Serial.print(" idle calibration failed with ");
      Serial.print(validReadings);
      Serial.print("/");
      Serial.print(CALIBRATION_SAMPLES);
      Serial.println(" valid readings");
    }
  }
  resetMovingAverages();
}

void calibrateSensors() {
  calibrateDetectionLimits();
  calibrateIdleBackground();
  Serial.println("Calibration complete");
}

uint8_t keyboardBatteryPercent(float voltage) {
  if (voltage <= KEYBOARD_BATTERY_EMPTY_V) {
    return 0;
  }
  if (voltage >= KEYBOARD_BATTERY_FULL_V) {
    return 100;
  }
  return static_cast<uint8_t>(lroundf(
    (voltage - KEYBOARD_BATTERY_EMPTY_V) * 100.0f /
    (KEYBOARD_BATTERY_FULL_V - KEYBOARD_BATTERY_EMPTY_V)
  ));
}

void setupKeyboardBatterySense() {
  pinMode(KEYBOARD_BATTERY_ADC_PIN, INPUT);
  analogReadResolution(12);
#if defined(ADC_11db)
  analogSetPinAttenuation(KEYBOARD_BATTERY_ADC_PIN, ADC_11db);
#endif
  Serial.print("[KEYBOARD] Battery divider ADC GPIO=");
  Serial.print(KEYBOARD_BATTERY_ADC_PIN);
  Serial.print(", ratio=");
  Serial.println(KEYBOARD_BATTERY_DIVIDER_RATIO, 2);
}

bool readKeyboardBattery(float &voltage, uint16_t &adcRaw, uint16_t &senseMv) {
  const uint8_t samples = 16;
  uint32_t rawSum = 0;
  uint32_t mvSum = 0;
  for (uint8_t i = 0; i < samples; ++i) {
    rawSum += analogRead(KEYBOARD_BATTERY_ADC_PIN);
    mvSum += analogReadMilliVolts(KEYBOARD_BATTERY_ADC_PIN);
    delay(2);
  }
  adcRaw = static_cast<uint16_t>((rawSum + samples / 2) / samples);
  senseMv = static_cast<uint16_t>((mvSum + samples / 2) / samples);
  voltage = (senseMv / 1000.0f) * KEYBOARD_BATTERY_DIVIDER_RATIO;
  return senseMv > 100 && voltage >= 2.0f && voltage <= 4.6f;
}

void printMacAddress(const uint8_t mac[6]) {
  for (int i = 0; i < 6; ++i) {
    if (i > 0) Serial.print(":");
    if (mac[i] < 0x10) Serial.print("0");
    Serial.print(mac[i], HEX);
  }
}

bool addAirTrixxPeer(const uint8_t mac[6]) {
  if (esp_now_is_peer_exist(mac)) {
    return true;
  }
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, mac, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;
  peer.ifidx = WIFI_IF_STA;
  esp_err_t result = esp_now_add_peer(&peer);
  if (result != ESP_OK) {
    Serial.print("[KEYBOARD] ESP-NOW add antenna peer failed: ");
    Serial.println(result);
    return false;
  }
  return true;
}

void handleAirTrixxCommandPacket(const uint8_t *data, int len) {
  if (data == nullptr || len < static_cast<int>(sizeof(AirTrixxPacketHeader))) {
    return;
  }
  AirTrixxPacketHeader header = {};
  memcpy(&header, data, sizeof(header));
  if (header.protocol_version != AIRTRIXX_PROTOCOL_VERSION ||
      header.msg_type != MSG_KEYBOARD_COMMAND ||
      len != static_cast<int>(sizeof(KeyboardCommandPacket))) {
    return;
  }

  KeyboardCommandPacket packet = {};
  memcpy(&packet, data, sizeof(packet));
  if (packet.header.device_id != DEVICE_ANTENNA) {
    return;
  }
  if (packet.command == KEYBOARD_CMD_RECALIBRATE) {
    airTrixxRecalibrationRequested = true;
  }
}

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
void onAirTrixxDataRecv(const esp_now_recv_info_t *info, const uint8_t *incomingData, int len) {
  (void)info;
  handleAirTrixxCommandPacket(incomingData, len);
}
#else
void onAirTrixxDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
  (void)mac;
  handleAirTrixxCommandPacket(incomingData, len);
}
#endif

void initAirTrixxWireless() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.disconnect();
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  esp_wifi_set_ps(WIFI_PS_NONE);
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);
  if (esp_now_init() != ESP_OK) {
    Serial.println("[KEYBOARD] ESP-NOW init failed");
    return;
  }
  esp_now_register_recv_cb(onAirTrixxDataRecv);
  addAirTrixxPeer(ANTENNA_MAC_PLACEHOLDER);
  airTrixxWirelessReady = true;

  uint8_t mac[6] = {};
  WiFi.macAddress(mac);
  Serial.print("[KEYBOARD] WiFi STA MAC=");
  printMacAddress(mac);
  Serial.print(", channel=");
  Serial.println(ESPNOW_CHANNEL);
}

void sendAirTrixxKeyboardTof(int rawMM[], bool rawValid[]) {
  unsigned long nowMs = millis();
  const unsigned long intervalMs = max(1UL, 1000UL / KEYBOARD_REPORT_HZ);
  if (nowMs - lastAirTrixxReportMs < intervalMs) {
    return;
  }
  lastAirTrixxReportMs = nowMs;

  KeyboardTofPacket packet = {};
  fillHeader(
    packet.header,
    MSG_KEYBOARD_TOF,
    DEVICE_KEYBOARD,
    ++airTrixxKeyboardSequence,
    nowMs,
    false
  );
  packet.distance_mm_1 = rawValid[0] && rawMM[0] > 0 ? rawMM[0] : 0;
  packet.distance_mm_2 = rawValid[1] && rawMM[1] > 0 ? rawMM[1] : 0;
  packet.distance_mm_3 = rawValid[2] && rawMM[2] > 0 ? rawMM[2] : 0;
  packet.distance_mm_4 = rawValid[3] && rawMM[3] > 0 ? rawMM[3] : 0;
  packet.valid_1 = rawValid[0] ? 1 : 0;
  packet.valid_2 = rawValid[1] ? 1 : 0;
  packet.valid_3 = rawValid[2] ? 1 : 0;
  packet.valid_4 = rawValid[3] ? 1 : 0;
  esp_now_send(ANTENNA_MAC_PLACEHOLDER, reinterpret_cast<uint8_t *>(&packet), sizeof(packet));
}

void airTrixxStartupBeaconTask(void *parameter) {
  (void)parameter;
  while (airTrixxStartupBeaconActive) {
    int rawMM[NUM_SENSORS];
    bool rawValid[NUM_SENSORS];
    for (uint8_t i = 0; i < NUM_SENSORS; ++i) {
      rawMM[i] = startupRawMM[i];
      rawValid[i] = startupRawValid[i];
    }
    sendAirTrixxKeyboardTof(rawMM, rawValid);
    delay(200);
  }
  vTaskDelete(nullptr);
}

void startAirTrixxStartupBeacon() {
  airTrixxStartupBeaconActive = true;
  xTaskCreate(airTrixxStartupBeaconTask, "keyboard_beacon", 3072, nullptr, 1, nullptr);
}

void sendAirTrixxKeyboardBattery(bool force) {
  unsigned long nowMs = millis();
  if (!force && airTrixxBatteryReportSent &&
      nowMs - lastAirTrixxBatteryReportMs < KEYBOARD_BATTERY_REPORT_MS) {
    return;
  }
  lastAirTrixxBatteryReportMs = nowMs;
  airTrixxBatteryReportSent = true;

  float batteryVoltage = 0.0f;
  uint16_t adcRaw = 0;
  uint16_t senseMv = 0;
  bool batteryValid = readKeyboardBattery(batteryVoltage, adcRaw, senseMv);
  uint8_t batteryPercent = batteryValid ? keyboardBatteryPercent(batteryVoltage) : 0;

  BatteryStatusPacket packet = {};
  fillHeader(
    packet.header,
    MSG_BATTERY_STATUS,
    DEVICE_KEYBOARD,
    ++airTrixxKeyboardBatterySequence,
    nowMs,
    batteryValid && batteryPercent <= 15
  );
  packet.battery_mv = batteryValid ? static_cast<uint16_t>(lroundf(batteryVoltage * 1000.0f)) : 0;
  packet.battery_percent = batteryPercent;
  packet.battery_valid = batteryValid ? 1 : 0;
  packet.battery_adc_raw = adcRaw;
  esp_now_send(ANTENNA_MAC_PLACEHOLDER, reinterpret_cast<uint8_t *>(&packet), sizeof(packet));
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(10);
  delay(20);
  initAirTrixxWireless();
  startAirTrixxStartupBeacon();
  Serial.print("I2C SDA="); Serial.print(I2C_SDA_PIN); Serial.print(" SCL="); Serial.println(I2C_SCL_PIN);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(100000);
  setupKeyboardBatterySense();
  sendAirTrixxKeyboardBattery(true);
  printChannelMappings();
  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
    uint8_t ch = keyMaps[i].ch;
    bool initialized = false;
    Serial.print("Init CH"); Serial.println(ch);
    for (uint8_t attempt = 1; attempt <= SENSOR_INIT_RETRIES; attempt++) {
      tcaSelect(ch);
      if (lox[i].begin()) {
        initialized = true;
        loxReady[i] = true;
        break;
      }
      delay(100);
    }
    if (!initialized) {
      loxReady[i] = false;
      Serial.print("WARNING: Sensor init failed CH");
      Serial.print(ch);
      Serial.print(" after ");
      Serial.print(SENSOR_INIT_RETRIES);
      Serial.println(" attempts");
      continue;
    }
    lox[i].setMeasurementTimingBudgetMicroSeconds(MEASUREMENT_BUDGET_US);
  }
  calibrateSensors();
  airTrixxStartupBeaconActive = false;
}

// ============================================================
// MAIN LOOP
// ============================================================
void loop() {
  handleSerialCommand();
  if (airTrixxRecalibrationRequested) {
    airTrixxRecalibrationRequested = false;
    Serial.println("[KEYBOARD] ESP-NOW recalibration requested");
    calibrateSensors();
  }
  sendAirTrixxKeyboardBattery(false);

  int relativePerCh[NUM_KEY_MAPS];
  int rawPerCh[NUM_KEY_MAPS];
  bool rawValid[NUM_KEY_MAPS];

  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
    uint8_t ch = keyMaps[i].ch;
    int rawMM;
    relativePerCh[i] = -1;
    rawValid[i] = readRaw(ch, rawMM);
    rawPerCh[i] = rawValid[i] ? rawMM : -1;
    if (rawValid[i]) addMovingSample(ch, rawMM);
  }

  for (uint8_t i = 0; i < NUM_KEY_MAPS; i++) {
    uint8_t ch = keyMaps[i].ch;
    int avgRawMM;
    if (!getMovingAverage(ch, avgRawMM)) continue;
    relativePerCh[i] = avgRawMM;
  }

  sendAirTrixxKeyboardTof(rawPerCh, rawValid);

  if (loggingMode) {
    if (!logHeaderPrinted) { printLogHeader(); logHeaderPrinted = true; }
    if (millis() - lastLogMs >= LOG_SAMPLE_INTERVAL_MS) { printLogRow(rawPerCh, rawValid, relativePerCh); lastLogMs = millis(); }
  }
}
