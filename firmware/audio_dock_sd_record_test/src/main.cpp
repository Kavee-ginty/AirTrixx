#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include <driver/i2s.h>

#define I2S_WS 7
#define I2S_SD 17
#define I2S_SCK 4
#define I2S_PORT I2S_NUM_0

#define SD_CS_PIN 47
#define SD_SCK_PIN 38
#define SD_MISO_PIN 40
#define SD_MOSI_PIN 39
#define SD_SPI_HZ 4000000

#define SAMPLE_RATE 16000
#define RECORD_SECONDS 3
#define RECORD_GAIN 32
#define WAV_HEADER_BYTES 44
#define AUDIO_DATA_BYTES (RECORD_SECONDS * SAMPLE_RATE * sizeof(int16_t))
#define AUDIO_TOTAL_BYTES (WAV_HEADER_BYTES + AUDIO_DATA_BYTES)

static const char *WAV_PATH = "/SDTEST.WAV";

static void writeLE16(uint8_t *buffer, size_t offset, uint16_t value) {
  buffer[offset + 0] = value & 0xFF;
  buffer[offset + 1] = (value >> 8) & 0xFF;
}

static void writeLE32(uint8_t *buffer, size_t offset, uint32_t value) {
  buffer[offset + 0] = value & 0xFF;
  buffer[offset + 1] = (value >> 8) & 0xFF;
  buffer[offset + 2] = (value >> 16) & 0xFF;
  buffer[offset + 3] = (value >> 24) & 0xFF;
}

static void writeWavHeader(uint8_t *buffer, uint32_t dataBytes) {
  const uint16_t channels = 1;
  const uint16_t bitsPerSample = 16;
  const uint32_t byteRate = SAMPLE_RATE * channels * (bitsPerSample / 8);
  const uint16_t blockAlign = channels * (bitsPerSample / 8);

  memcpy(buffer + 0, "RIFF", 4);
  writeLE32(buffer, 4, 36 + dataBytes);
  memcpy(buffer + 8, "WAVE", 4);
  memcpy(buffer + 12, "fmt ", 4);
  writeLE32(buffer, 16, 16);
  writeLE16(buffer, 20, 1);
  writeLE16(buffer, 22, channels);
  writeLE32(buffer, 24, SAMPLE_RATE);
  writeLE32(buffer, 28, byteRate);
  writeLE16(buffer, 32, blockAlign);
  writeLE16(buffer, 34, bitsPerSample);
  memcpy(buffer + 36, "data", 4);
  writeLE32(buffer, 40, dataBytes);
}

static bool setupI2SMic() {
  i2s_config_t i2sConfig = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 512,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pinConfig = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2sConfig, 0, nullptr);
  if (err != ESP_OK) {
    Serial.printf("I2S install failed: %d\n", err);
    return false;
  }

  err = i2s_set_pin(I2S_PORT, &pinConfig);
  if (err != ESP_OK) {
    Serial.printf("I2S pin setup failed: %d\n", err);
    i2s_driver_uninstall(I2S_PORT);
    return false;
  }

  i2s_zero_dma_buffer(I2S_PORT);
  return true;
}

static bool setupSD() {
  pinMode(SD_CS_PIN, OUTPUT);
  digitalWrite(SD_CS_PIN, HIGH);
  delay(10);

  SPI.begin(SD_SCK_PIN, SD_MISO_PIN, SD_MOSI_PIN, SD_CS_PIN);
  Serial.printf("SD init: CS=%u SCK=%u MISO=%u MOSI=%u hz=%u\n",
                SD_CS_PIN,
                SD_SCK_PIN,
                SD_MISO_PIN,
                SD_MOSI_PIN,
                SD_SPI_HZ);

  if (!SD.begin(SD_CS_PIN, SPI, SD_SPI_HZ)) {
    Serial.println("SD init failed.");
    return false;
  }

  Serial.printf("SD ready. Card type=%u\n", SD.cardType());
  return true;
}

static void flushI2S() {
  int32_t discard[128];
  size_t bytesRead = 0;
  const uint32_t untilMs = millis() + 250;
  while (millis() < untilMs) {
    i2s_read(I2S_PORT, discard, sizeof(discard), &bytesRead, 20 / portTICK_PERIOD_MS);
  }
}

static bool recordWavToSD() {
  SD.remove(WAV_PATH);
  File file = SD.open(WAV_PATH, FILE_WRITE);
  if (!file) {
    Serial.printf("Failed to open %s for write.\n", WAV_PATH);
    return false;
  }

  uint8_t header[WAV_HEADER_BYTES];
  writeWavHeader(header, AUDIO_DATA_BYTES);
  if (file.write(header, sizeof(header)) != sizeof(header)) {
    Serial.println("Failed to write WAV header.");
    file.close();
    return false;
  }

  flushI2S();
  Serial.printf("RECORD_START seconds=%u path=%s expected_bytes=%u\n",
                RECORD_SECONDS,
                WAV_PATH,
                AUDIO_TOTAL_BYTES);

  uint32_t samplesWritten = 0;
  int32_t i2sBuffer[512];
  int16_t pcmBuffer[512];
  const uint32_t totalSamples = RECORD_SECONDS * SAMPLE_RATE;
  const uint32_t startedAt = millis();

  while (samplesWritten < totalSamples) {
    const uint32_t samplesToRead = min<uint32_t>(512, totalSamples - samplesWritten);
    size_t bytesRead = 0;
    esp_err_t err = i2s_read(I2S_PORT,
                             i2sBuffer,
                             samplesToRead * sizeof(int32_t),
                             &bytesRead,
                             portMAX_DELAY);
    if (err != ESP_OK || bytesRead == 0) {
      Serial.printf("I2S read failed: err=%d bytes=%u\n", err, (unsigned int)bytesRead);
      file.close();
      return false;
    }

    const size_t samples = bytesRead / sizeof(int32_t);
    for (size_t i = 0; i < samples; i++) {
      int32_t sample = (i2sBuffer[i] >> 14) * RECORD_GAIN;
      sample = constrain(sample, -32768, 32767);
      pcmBuffer[i] = (int16_t)sample;
    }

    const size_t bytesToWrite = samples * sizeof(int16_t);
    if (file.write((const uint8_t *)pcmBuffer, bytesToWrite) != bytesToWrite) {
      Serial.println("SD audio write failed.");
      file.close();
      return false;
    }

    samplesWritten += samples;
    if ((samplesWritten % SAMPLE_RATE) < samples) {
      Serial.printf("Recording progress: %lu/%lu samples\n",
                    (unsigned long)samplesWritten,
                    (unsigned long)totalSamples);
    }
  }

  file.flush();
  const uint32_t finalSize = file.size();
  file.close();

  Serial.printf("RECORD_DONE ms=%lu bytes=%u path=%s\n",
                (unsigned long)(millis() - startedAt),
                (unsigned int)finalSize,
                WAV_PATH);
  Serial.println(finalSize == AUDIO_TOTAL_BYTES ? "WAV_SIZE_OK" : "WAV_SIZE_MISMATCH");
  return finalSize == AUDIO_TOTAL_BYTES;
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("Audio Dock SD 3-second recording test");

  if (!setupSD()) {
    Serial.println("TEST_FAIL: SD setup failed");
    return;
  }

  if (!setupI2SMic()) {
    Serial.println("TEST_FAIL: I2S setup failed");
    return;
  }

  bool ok = recordWavToSD();
  i2s_driver_uninstall(I2S_PORT);
  Serial.println(ok ? "TEST_PASS" : "TEST_FAIL");
}

void loop() {
  delay(1000);
}
