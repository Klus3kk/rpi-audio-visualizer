#include <Arduino.h>
#include <FastLED.h>

#define WIDTH 16
#define HEIGHT 16
#define NUM_LEDS (WIDTH * HEIGHT)

#define DATA_PIN 18
#define LED_TYPE WS2812B
#define COLOR_ORDER GRB
#define BRIGHTNESS 10

static const uint32_t SERIAL_BAUD = 115200;   // ważne: ustawimy tak samo na Pi
static const uint32_t WATCHDOG_MS = 600;

CRGB leds[NUM_LEDS];

// serpentine
static inline uint16_t XY(uint8_t x, uint8_t y) {
  if ((y & 1) == 0) return (uint16_t)y * WIDTH + x;
  return (uint16_t)y * WIDTH + (WIDTH - 1 - x);
}

// CRC8 poly 0x07
static uint8_t crc8(const uint8_t* data, size_t len) {
  uint8_t crc = 0;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

enum class RxState { SYNC1, SYNC2, FRAME_ID, LEN1, LEN2, PAYLOAD, CRC };
static RxState st = RxState::SYNC1;

static uint8_t frameId = 0;
static uint16_t wantLen = 0;
static uint16_t got = 0;

static uint8_t payload[NUM_LEDS * 3];
static uint32_t lastOkFrameMs = 0;

static void applyPayload() {
  int p = 0;
  for (int y = 0; y < HEIGHT; y++) {
    for (int x = 0; x < WIDTH; x++) {
      uint8_t r = payload[p++];
      uint8_t g = payload[p++];
      uint8_t b = payload[p++];
      leds[XY((uint8_t)x, (uint8_t)y)] = CRGB(r, g, b);
    }
  }
  FastLED.show();
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(150);

  FastLED.addLeds<LED_TYPE, DATA_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(BRIGHTNESS);
  fill_solid(leds, NUM_LEDS, CRGB::Black);
  FastLED.show();

  // Boot marker: krótkie mignięcie na fiolet
  fill_solid(leds, NUM_LEDS, CRGB(80, 0, 120));
  FastLED.show();
  delay(150);
  fill_solid(leds, NUM_LEDS, CRGB::Black);
  FastLED.show();

  lastOkFrameMs = millis();
}

void loop() {
  // watchdog: jeśli brak poprawnych ramek -> gaś
  if (millis() - lastOkFrameMs > WATCHDOG_MS) {
    fill_solid(leds, NUM_LEDS, CRGB::Black);
    FastLED.show();
    // nie resetuj lastOkFrameMs, żeby stale było czarne aż do pierwszej poprawnej ramki
  }

  while (Serial.available() > 0) {
    uint8_t b = (uint8_t)Serial.read();

    switch (st) {
      case RxState::SYNC1:
        if (b == 0xAA) st = RxState::SYNC2;
        break;

      case RxState::SYNC2:
        if (b == 0x55) {
          st = RxState::FRAME_ID;
        } else {
          st = RxState::SYNC1;
        }
        break;

      case RxState::FRAME_ID:
        frameId = b;
        st = RxState::LEN1;
        break;

      case RxState::LEN1:
        wantLen = b;
        st = RxState::LEN2;
        break;

      case RxState::LEN2:
        wantLen |= ((uint16_t)b << 8);
        if (wantLen != (NUM_LEDS * 3)) {
          st = RxState::SYNC1;
        } else {
          got = 0;
          st = RxState::PAYLOAD;
        }
        break;

      case RxState::PAYLOAD:
        payload[got++] = b;
        if (got >= wantLen) st = RxState::CRC;
        break;

      case RxState::CRC: {
        uint8_t recv = b;
        uint8_t calc = crc8(payload, wantLen);
        if (recv == calc) {
          applyPayload();
          lastOkFrameMs = millis();
        }
        st = RxState::SYNC1;
      } break;
    }
  }
}
