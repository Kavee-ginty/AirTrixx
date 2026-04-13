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

static const uint8_t SERVO_CH_START = 10;
static const uint8_t SERVO_CH_END   = 15;
static const uint16_t SERVO_MID = 375;

static const uint8_t ESPNOW_CHANNEL = 1;

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
WristbandPacket latestPacket{};
uint8_t latestSenderMac[6] = {0};

bool i2cDevicePresent(TwoWire &bus, uint8_t address) {
    bus.beginTransmission(address);
    return (bus.endTransmission() == 0);
}

void tcaSelect(uint8_t channel) {
    if (channel > 7) return;
    ToFBus.beginTransmission(TCA9548A_ADDR);
    ToFBus.write(1 << channel);
    ToFBus.endTransmission();
    delay(5);
}

void tcaDisableAll() {
    ToFBus.beginTransmission(TCA9548A_ADDR);
    ToFBus.write(0x00);
    ToFBus.endTransmission();
    delay(5);
}

bool initPCA9685() {
    if (!i2cDevicePresent(ServoBus, PCA9685_ADDR)) {
        Serial.println("[PCA9685] Not found");
        return false;
    }

    pwm.begin();
    pwm.setPWMFreq(50);
    delay(10);

    for (uint8_t ch = SERVO_CH_START; ch <= SERVO_CH_END; ch++) {
        pwm.setPWM(ch, 0, SERVO_MID);
    }

    Serial.println("[PCA9685] Initialized");
    return true;
}

bool initToFSensorOnChannel(uint8_t muxChannel, const char *label) {
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
    if (len != (int)sizeof(WristbandPacket)) {
        return;
    }

    WristbandPacket temp;
    memcpy(&temp, data, sizeof(temp));

    if (temp.magic != 0xA17A1234 || temp.version != 1) {
        return;
    }

    memcpy((void *)&latestPacket, &temp, sizeof(temp));
    memcpy((void *)latestSenderMac, mac, 6);
    wristPacketAvailable = true;
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

void printMac(const uint8_t *mac) {
    Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void setup() {
    Serial.begin(115200);
    delay(3000);

    Serial.println();
    Serial.println("=== AirTrixx CamDock ESP-NOW Receiver ===");

    ServoBus.begin(SERVO_SDA, SERVO_SCL);
    ToFBus.begin(TOF_SDA, TOF_SCL);
    delay(100);

    initPCA9685();
    initToFSensorOnChannel(TOF_LEFT_MUX_CH, "TOF-CH1");
    initToFSensorOnChannel(TOF_RIGHT_MUX_CH, "TOF-CH2");

    if (!setupEspNow()) {
        Serial.println("ESP-NOW setup failed");
        while (true) {
            delay(1000);
        }
    }

    Serial.print("CamDock STA MAC: ");
    Serial.println(WiFi.macAddress());
    Serial.println("ESP-NOW receiver ready");
}

void loop() {
    static uint32_t lastPrint = 0;

    if (millis() - lastPrint >= 200) {
        lastPrint = millis();

        int16_t d1 = readToFDistanceMm(TOF_LEFT_MUX_CH);
        int16_t d2 = readToFDistanceMm(TOF_RIGHT_MUX_CH);

        Serial.printf("TOF | CH1=%d mm | CH2=%d mm", d1, d2);

        if (wristPacketAvailable) {
            WristbandPacket p;
            uint8_t mac[6];

            noInterrupts();
            memcpy(&p, &latestPacket, sizeof(p));
            memcpy(mac, latestSenderMac, 6);
            interrupts();

            Serial.print(" || RX from ");
            printMac(mac);
            Serial.printf(" | seq=%u | A:%d,%d,%d | G:%d,%d,%d | M:%d,%d,%d",
                          p.seq,
                          p.ax, p.ay, p.az,
                          p.gx, p.gy, p.gz,
                          p.mx, p.my, p.mz);
        } else {
            Serial.print(" || No wrist packet yet");
        }

        Serial.println();
    }
}