#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

static const uint8_t ENC_CLK = 7;
static const uint8_t ENC_DT = 1;
static const uint8_t ENC_SW = 2;
static const uint8_t I2C_SDA = 10;
static const uint8_t I2C_SCL = 9;

static const uint8_t SCREEN_WIDTH = 128;
static const uint8_t SCREEN_HEIGHT = 64;
static const uint8_t WINDOW_COUNT = 5;
static const uint32_t SERIAL_PRINT_INTERVAL_MS = 120;
static const uint32_t BUTTON_DEBOUNCE_MS = 250;

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

static long encoderCount = 0;
static long minCount = 0;
static long maxCount = 0;
static long sessionStartCount = 0;
static long sessionMinCount = 0;
static long sessionMaxCount = 0;
static long lastReportedCount = LONG_MIN;

static int lastClk = HIGH;
static bool lastButtonState = HIGH;
static uint32_t lastSerialPrintMs = 0;
static uint32_t lastButtonMs = 0;
static bool displayReady = false;
static bool captureActive = false;
static uint8_t currentWindow = 0;

static void printInstructions() {
  Serial.println();
  Serial.println("=== Rotary Encoder Calibration ===");
  Serial.println("Press encoder button to reset and start a capture.");
  Serial.println("Rotate one full circle in one direction.");
  Serial.println("Press the button again to end the capture.");
  Serial.println("Copy the serial output and paste it in chat.");
  Serial.println("Expected log lines:");
  Serial.println("CAL_POINT,count=<n>,delta=<n>,window=<n>");
  Serial.println("CAL_DONE,start=<n>,end=<n>,min=<n>,max=<n>,span=<n>");
  Serial.println();
}

static void updateWindowEstimate() {
  long span = maxCount - minCount;
  if (span < static_cast<long>(WINDOW_COUNT)) {
    currentWindow = 0;
    return;
  }

  long offset = encoderCount - minCount;
  long segment = span / WINDOW_COUNT;
  if (segment <= 0) {
    currentWindow = 0;
    return;
  }

  long idx = offset / segment;
  if (idx < 0) idx = 0;
  if (idx >= WINDOW_COUNT) idx = WINDOW_COUNT - 1;
  currentWindow = static_cast<uint8_t>(idx);
}

static void drawDisplay() {
  if (!displayReady) return;

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("ENC CALIBRATION");

  display.setCursor(0, 14);
  display.print("Count: ");
  display.println(encoderCount);

  display.setCursor(0, 26);
  display.print("Min: ");
  display.print(minCount);
  display.print(" Max: ");
  display.println(maxCount);

  display.setCursor(0, 38);
  if (captureActive) {
    display.print("Capture: RUN");
  } else {
    display.print("Capture: IDLE");
  }

  display.setCursor(0, 50);
  display.print("Window: ");
  display.print(currentWindow + 1);
  display.print("/");
  display.println(WINDOW_COUNT);

  display.display();
}

static void beginCapture() {
  captureActive = true;
  sessionStartCount = encoderCount;
  sessionMinCount = encoderCount;
  sessionMaxCount = encoderCount;
  Serial.println("CAL_START");
  Serial.print("CAL_POINT,count=");
  Serial.print(encoderCount);
  Serial.print(",delta=0,window=");
  Serial.println(currentWindow);
}

static void endCapture() {
  captureActive = false;
  long span = sessionMaxCount - sessionMinCount;
  Serial.print("CAL_DONE,start=");
  Serial.print(sessionStartCount);
  Serial.print(",end=");
  Serial.print(encoderCount);
  Serial.print(",min=");
  Serial.print(sessionMinCount);
  Serial.print(",max=");
  Serial.print(sessionMaxCount);
  Serial.print(",span=");
  Serial.println(span);
}

static void handleButton() {
  bool buttonState = digitalRead(ENC_SW);
  uint32_t now = millis();
  if (lastButtonState == HIGH && buttonState == LOW &&
      now - lastButtonMs >= BUTTON_DEBOUNCE_MS) {
    lastButtonMs = now;
    if (captureActive) {
      endCapture();
    } else {
      beginCapture();
    }
  }
  lastButtonState = buttonState;
}

static void maybePrintCalibrationPoint() {
  uint32_t now = millis();
  if (encoderCount == lastReportedCount && now - lastSerialPrintMs < SERIAL_PRINT_INTERVAL_MS) {
    return;
  }

  if (encoderCount != lastReportedCount) {
    lastReportedCount = encoderCount;
    lastSerialPrintMs = now;

    if (captureActive) {
      if (encoderCount < sessionMinCount) sessionMinCount = encoderCount;
      if (encoderCount > sessionMaxCount) sessionMaxCount = encoderCount;
    }

    Serial.print("CAL_POINT,count=");
    Serial.print(encoderCount);
    Serial.print(",delta=");
    Serial.print(encoderCount - sessionStartCount);
    Serial.print(",window=");
    Serial.println(currentWindow);
  }
}

static void handleEncoder() {
  int clk = digitalRead(ENC_CLK);
  if (clk != lastClk && clk == LOW) {
    if (digitalRead(ENC_DT) != clk) {
      ++encoderCount;
    } else {
      --encoderCount;
    }

    if (encoderCount < minCount) minCount = encoderCount;
    if (encoderCount > maxCount) maxCount = encoderCount;
    updateWindowEstimate();
    maybePrintCalibrationPoint();
  }
  lastClk = clk;
}

void setup() {
  Serial.begin(115200);
  delay(250);

  pinMode(ENC_CLK, INPUT_PULLUP);
  pinMode(ENC_DT, INPUT_PULLUP);
  pinMode(ENC_SW, INPUT_PULLUP);
  lastClk = digitalRead(ENC_CLK);
  lastButtonState = digitalRead(ENC_SW);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);
  displayReady = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);

  printInstructions();
  if (displayReady) {
    drawDisplay();
  } else {
    Serial.println("OLED not found at 0x3C. Serial calibration still works.");
  }
}

void loop() {
  handleEncoder();
  handleButton();
  updateWindowEstimate();
  drawDisplay();
  delay(2);
}
