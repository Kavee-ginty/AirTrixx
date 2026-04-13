#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

static const uint8_t I2C_SDA = 8;
static const uint8_t I2C_SCL = 9;

static const uint8_t MPU_ADDR = 0x68;
static const uint8_t QMC_ADDR = 0x0D;

static const uint8_t ESPNOW_CHANNEL = 1;

// CamDock STA MAC
static uint8_t CAMDOCK_MAC[] = {0x10, 0x20, 0xBA, 0x4C, 0x5B, 0xF4};

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

static WristbandPacket txPacket{};
static uint16_t seqCounter = 0;
static volatile esp_now_send_status_t lastSendStatus = ESP_NOW_SEND_FAIL;

void writeByte(uint8_t dev, uint8_t reg, uint8_t data) {
    Wire.beginTransmission(dev);
    Wire.write(reg);
    Wire.write(data);
    Wire.endTransmission();
}

bool readBytes(uint8_t dev, uint8_t reg, uint8_t *buffer, size_t len) {
    Wire.beginTransmission(dev);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) {
        return false;
    }

    size_t count = Wire.requestFrom((int)dev, (int)len);
    if (count != len) {
        return false;
    }

    for (size_t i = 0; i < len; i++) {
        buffer[i] = Wire.read();
    }
    return true;
}

void setupMPU6050() {
    // Wake
    writeByte(MPU_ADDR, 0x6B, 0x00);
    delay(50);

    // Gyro ±250 dps
    writeByte(MPU_ADDR, 0x1B, 0x00);
    delay(10);

    // Accel ±2g
    writeByte(MPU_ADDR, 0x1C, 0x00);
    delay(10);
}

bool readMPU6050(int16_t &ax, int16_t &ay, int16_t &az,
                 int16_t &gx, int16_t &gy, int16_t &gz) {
    uint8_t data[14];

    if (!readBytes(MPU_ADDR, 0x3B, data, 14)) {
        return false;
    }

    ax = (int16_t)((data[0] << 8) | data[1]);
    ay = (int16_t)((data[2] << 8) | data[3]);
    az = (int16_t)((data[4] << 8) | data[5]);

    gx = (int16_t)((data[8] << 8) | data[9]);
    gy = (int16_t)((data[10] << 8) | data[11]);
    gz = (int16_t)((data[12] << 8) | data[13]);

    return true;
}

void setupQMC5883L() {
    // OSR=512, RNG=8G, ODR=100Hz, MODE=continuous
    writeByte(QMC_ADDR, 0x09, 0x1D);
    delay(50);
}

bool readQMC5883L(int16_t &mx, int16_t &my, int16_t &mz) {
    uint8_t data[6];

    if (!readBytes(QMC_ADDR, 0x00, data, 6)) {
        return false;
    }

    mx = (int16_t)((data[1] << 8) | data[0]);
    my = (int16_t)((data[3] << 8) | data[2]);
    mz = (int16_t)((data[5] << 8) | data[4]);

    return true;
}

void onDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
    (void)mac_addr;
    lastSendStatus = status;
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

    esp_now_register_send_cb(onDataSent);

    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, CAMDOCK_MAC, 6);
    peerInfo.channel = ESPNOW_CHANNEL;
    peerInfo.encrypt = false;

    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
        Serial.println("esp_now_add_peer failed");
        return false;
    }

    return true;
}

void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println();
    Serial.println("=== AirTrixx Wristband Sender ===");

    Wire.begin(I2C_SDA, I2C_SCL);
    delay(50);

    setupMPU6050();
    setupQMC5883L();

    if (!setupEspNow()) {
        Serial.println("ESP-NOW setup failed");
        while (true) delay(1000);
    }

    Serial.print("Wristband MAC: ");
    Serial.println(WiFi.macAddress());
    Serial.println("Sender ready");
}

void loop() {
    static uint32_t lastSend = 0;

    if (millis() - lastSend >= 10) { // 100 Hz
        lastSend = millis();

        int16_t ax, ay, az, gx, gy, gz, mx, my, mz;

        bool mpuOk = readMPU6050(ax, ay, az, gx, gy, gz);
        bool qmcOk = readQMC5883L(mx, my, mz);

        if (!mpuOk || !qmcOk) {
            return;
        }

        txPacket.magic = 0xA17A1234;
        txPacket.version = 1;
        txPacket.seq = seqCounter++;
        txPacket.uptime_ms = millis();

        txPacket.ax = ax;
        txPacket.ay = ay;
        txPacket.az = az;

        txPacket.gx = gx;
        txPacket.gy = gy;
        txPacket.gz = gz;

        txPacket.mx = mx;
        txPacket.my = my;
        txPacket.mz = mz;

        esp_now_send(CAMDOCK_MAC, (uint8_t *)&txPacket, sizeof(txPacket));
    }
}