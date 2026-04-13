#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Adafruit_PWMServoDriver.h>
#include <VL53L1X.h>

TwoWire ServoBus = TwoWire(0);
TwoWire ToFBus   = TwoWire(1);

static const uint8_t SERVO_SDA = 18;
static const uint8_t SERVO_SCL = 21;

static const uint8_t TOF_SDA = 15;
static const uint8_t TOF_SCL = 17;

static const uint8_t PCA9685_ADDR = 0x40;
static const uint8_t TCA9548A_ADDR = 0x70;

static const uint8_t TOF_LEFT_MUX_CH  = 1;
static const uint8_t TOF_RIGHT_MUX_CH = 2;

static const uint8_t ESPNOW_CHANNEL = 1;

// Actual servo mapping
static const uint8_t CH_R_PAN    = 10;
static const uint8_t CH_R_TILT   = 11;
static const uint8_t CH_CAM_PAN  = 12;
static const uint8_t CH_CAM_TILT = 13;
static const uint8_t CH_L_PAN    = 14;
static const uint8_t CH_L_TILT   = 15;

// Servo safety range
static const uint16_t SERVO_MIN_US = 900;
static const uint16_t SERVO_MAX_US = 2100;

// Servo neutral positions
static const uint16_t CAM_PAN_CENTER_US  = 1500;
static const uint16_t CAM_TILT_CENTER_US = 1500;

static const uint16_t L_PAN_CENTER_US    = 1500;
static const uint16_t L_TILT_CENTER_US   = 1500;

static const uint16_t R_PAN_CENTER_US    = 1500;
static const uint16_t R_TILT_CENTER_US   = 1500;

static const uint32_t TELEMETRY_PERIOD_MS = 20; // 50 Hz

struct __attribute__((packed)) WristbandPacket {
    uint32_t magic;
    uint16_t version;
    uint16_t seq;
    uint32_t uptime_ms;

    int16_t ax;
    int16_t ay;
    int16_t az;

    int16_t gx;
    int16_t gy;
    int16_t gz;

    int16_t mx;
    int16_t my;
    int16_t mz;
};

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(PCA9685_ADDR, ServoBus);
VL53L1X tof;

volatile bool wristPacketAvailable = false;
volatile uint32_t lastWristRxMs = 0;
WristbandPacket latestPacket{};

uint16_t camPanUs  = CAM_PAN_CENTER_US;
uint16_t camTiltUs = CAM_TILT_CENTER_US;

uint16_t lPanUs    = L_PAN_CENTER_US;
uint16_t lTiltUs   = L_TILT_CENTER_US;

uint16_t rPanUs    = R_PAN_CENTER_US;
uint16_t rTiltUs   = R_TILT_CENTER_US;

bool i2cDevicePresent(TwoWire &bus, uint8_t address) {
    bus.beginTransmission(address);
    return (bus.endTransmission() == 0);
}

uint16_t clampUs(uint16_t us) {
    if (us < SERVO_MIN_US) return SERVO_MIN_US;
    if (us > SERVO_MAX_US) return SERVO_MAX_US;
    return us;
}

void applyServoUs(uint8_t ch, uint16_t us) {
    pwm.writeMicroseconds(ch, clampUs(us));
}

void applyAllServos() {
    applyServoUs(CH_CAM_PAN,  camPanUs);
    applyServoUs(CH_CAM_TILT, camTiltUs);

    applyServoUs(CH_L_PAN,    lPanUs);
    applyServoUs(CH_L_TILT,   lTiltUs);

    applyServoUs(CH_R_PAN,    rPanUs);
    applyServoUs(CH_R_TILT,   rTiltUs);
}

void centerAllServos() {
    camPanUs  = CAM_PAN_CENTER_US;
    camTiltUs = CAM_TILT_CENTER_US;

    lPanUs    = L_PAN_CENTER_US;
    lTiltUs   = L_TILT_CENTER_US;

    rPanUs    = R_PAN_CENTER_US;
    rTiltUs   = R_TILT_CENTER_US;

    applyAllServos();
}

void tcaSelect(uint8_t channel) {
    if (channel > 7) return;
    ToFBus.beginTransmission(TCA9548A_ADDR);
    ToFBus.write(1 << channel);
    ToFBus.endTransmission();
}

void tcaDisableAll() {
    ToFBus.beginTransmission(TCA9548A_ADDR);
    ToFBus.write(0x00);
    ToFBus.endTransmission();
}

bool initPCA9685() {
    if (!i2cDevicePresent(ServoBus, PCA9685_ADDR)) {
        Serial.println("[PCA9685] Not found");
        return false;
    }

    pwm.begin();
    pwm.setPWMFreq(50);
    delay(10);
    centerAllServos();

    Serial.println("[PCA9685] Initialized");
    return true;
}

bool initToFChannel(uint8_t muxChannel, const char *label) {
    tcaSelect(muxChannel);

    tof.setBus(&ToFBus);
    tof.setTimeout(100);

    if (!tof.init()) {
        Serial.printf("[%s] VL53L1X init FAILED on mux channel %u\n", label, muxChannel);
        tcaDisableAll();
        return false;
    }

    tof.setDistanceMode(VL53L1X::Long);
    tof.setMeasurementTimingBudget(50000);
    tof.startContinuous(50);

    Serial.printf("[%s] VL53L1X init OK on mux channel %u\n", label, muxChannel);
    tcaDisableAll();
    return true;
}

int16_t readToFDistanceMm(uint8_t muxChannel) {
    tcaSelect(muxChannel);
    uint16_t mm = tof.read();
    bool timeout = tof.timeoutOccurred();
    tcaDisableAll();

    if (timeout) return -1;
    return (int16_t)mm;
}

void onDataRecv(const uint8_t *mac, const uint8_t *data, int len) {
    (void)mac;

    if (len != (int)sizeof(WristbandPacket)) {
        return;
    }

    WristbandPacket temp;
    memcpy(&temp, data, sizeof(temp));

    if (temp.magic != 0xA17A1234 || temp.version != 1) {
        return;
    }

    latestPacket = temp;
    wristPacketAvailable = true;
    lastWristRxMs = millis();
}

bool setupEspNow() {
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    esp_err_t err = esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    if (err != ESP_OK) {
        Serial.printf("esp_wifi_set_channel failed: %d\n", err);
        return false;
    }

    if (esp_now_init() != ESP_OK) {
        Serial.println("esp_now_init failed");
        return false;
    }

    if (esp_now_register_recv_cb(onDataRecv) != ESP_OK) {
        Serial.println("esp_now_register_recv_cb failed");
        return false;
    }

    return true;
}

void handleSerialCommands() {
    static char buf[128];
    static uint8_t n = 0;

    while (Serial.available()) {
        char c = (char)Serial.read();

        if (c == '\r' || c == '\n') {
            if (n == 0) continue;
            buf[n] = 0;

            // SVA,camPan,camTilt,lPan,lTilt,rPan,rTilt
            if (!strncmp(buf, "SVA,", 4)) {
                int a, b, c1, d, e, f;
                if (sscanf(buf, "SVA,%d,%d,%d,%d,%d,%d", &a, &b, &c1, &d, &e, &f) == 6) {
                    camPanUs  = clampUs((uint16_t)a);
                    camTiltUs = clampUs((uint16_t)b);
                    lPanUs    = clampUs((uint16_t)c1);
                    lTiltUs   = clampUs((uint16_t)d);
                    rPanUs    = clampUs((uint16_t)e);
                    rTiltUs   = clampUs((uint16_t)f);
                    applyAllServos();
                }
            } else if (!strcmp(buf, "CENTER")) {
                centerAllServos();
            } else if (!strcmp(buf, "PING")) {
                Serial.println("PONG");
            }

            n = 0;
        } else {
            if (n < sizeof(buf) - 1) {
                buf[n++] = c;
            }
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println();
    Serial.println("=== AirTrixx CamDock ===");

    ServoBus.begin(SERVO_SDA, SERVO_SCL);
    ToFBus.begin(TOF_SDA, TOF_SCL);
    delay(50);

    initPCA9685();
    initToFChannel(TOF_LEFT_MUX_CH, "TOF-L");
    initToFChannel(TOF_RIGHT_MUX_CH, "TOF-R");

    if (!setupEspNow()) {
        Serial.println("ESP-NOW setup failed");
        while (true) delay(1000);
    }

    Serial.print("CamDock STA MAC: ");
    Serial.println(WiFi.macAddress());
    Serial.println("Ready");
}

void loop() {
    handleSerialCommands();

    static uint32_t lastPrint = 0;
    if (millis() - lastPrint >= TELEMETRY_PERIOD_MS) {
        lastPrint = millis();

        int16_t tofL = readToFDistanceMm(TOF_LEFT_MUX_CH);
        int16_t tofR = readToFDistanceMm(TOF_RIGHT_MUX_CH);

        bool wbValid = wristPacketAvailable && ((millis() - lastWristRxMs) < 250);

        WristbandPacket p{};
        if (wbValid) {
            noInterrupts();
            memcpy(&p, &latestPacket, sizeof(p));
            interrupts();
        }

        // CD,ms,wb_valid,seq,uptime,ax,ay,az,gx,gy,gz,mx,my,mz,tofL,tofR
        Serial.printf("CD,%lu,%d,%u,%lu,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
                      (unsigned long)millis(),
                      wbValid ? 1 : 0,
                      wbValid ? p.seq : 0,
                      (unsigned long)(wbValid ? p.uptime_ms : 0),
                      wbValid ? p.ax : 0,
                      wbValid ? p.ay : 0,
                      wbValid ? p.az : 0,
                      wbValid ? p.gx : 0,
                      wbValid ? p.gy : 0,
                      wbValid ? p.gz : 0,
                      wbValid ? p.mx : 0,
                      wbValid ? p.my : 0,
                      wbValid ? p.mz : 0,
                      tofL,
                      tofR);
    }
}