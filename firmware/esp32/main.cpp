#include <Arduino.h>
#include <FastLED.h>

#define W 16
#define H 16
#define NUM_LEDS (W*H)
#define DATA_PIN 18

// 1) ZMIEJSZ TO:
#define BRIGHTNESS 2          // 1..4 (spróbuj 1 lub 2)

// 2) LIMIT MOCY (bardzo ważne):
#define MAX_MILLIAMPS 250     // 150..350 zwykle OK na testy

#define SYNC1 0xAA
#define SYNC2 0x55
#define FRAME_LEN (NUM_LEDS*3)

CRGB leds[NUM_LEDS];
static uint8_t payload[FRAME_LEN];

inline uint16_t XY(uint8_t x, uint8_t y) {
  return (y & 1) ? (y*W + (W-1-x)) : (y*W + x);
}

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

static bool read_exact(uint8_t* out, size_t n) {
  size_t got = 0;
  while (got < n) {
    int c = Serial.read();
    if (c < 0) return false;   // jeszcze nie ma danych -> wróć do loop()
    out[got++] = (uint8_t)c;
  }
  return true;
}

// skala 0..255 bez floatów
static inline uint8_t scale8(uint8_t v, uint8_t s) {
  return (uint16_t(v) * uint16_t(s)) >> 8;
}

void setup() {
  Serial.begin(115200);
  delay(50);

  Serial.setRxBufferSize(4096);

  FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(BRIGHTNESS);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MILLIAMPS);

  fill_solid(leds, NUM_LEDS, CRGB::Black);
  FastLED.show();
}

void loop() {
  while (Serial.available() > 0) {
    int b = Serial.read();
    if (b != SYNC1) continue;

    uint8_t b2;
    if (!read_exact(&b2, 1)) return;
    if (b2 != SYNC2) continue;

    // frame_id (ignorujemy)
    uint8_t fid;
    if (!read_exact(&fid, 1)) return;

    // len lo/hi
    uint8_t l0, l1;
    if (!read_exact(&l0, 1)) return;
    if (!read_exact(&l1, 1)) return;

    uint16_t wantLen = (uint16_t)l0 | ((uint16_t)l1 << 8);
    if (wantLen != FRAME_LEN) continue;

    if (!read_exact(payload, FRAME_LEN)) return;

    uint8_t recvCrc;
    if (!read_exact(&recvCrc, 1)) return;
    if (recvCrc != crc8(payload, FRAME_LEN)) continue;

    int p = 0;
    for (uint8_t y = 0; y < H; y++) {
      for (uint8_t x = 0; x < W; x++) {
        uint8_t r = payload[p++];
        uint8_t g = payload[p++];
        uint8_t b = payload[p++];

        leds[XY(x,y)] = CRGB(r,g,b);
      }
    }
    FastLED.show();
  }
}
