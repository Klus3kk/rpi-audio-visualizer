#!/usr/bin/env python3
import os, time, math, serial
import numpy as np
import sounddevice as sd

# ===== ESP CONFIG =====
PORT = os.environ.get("ESP_PORT", "/dev/ttyUSB0")
BAUD = int(os.environ.get("ESP_BAUD", "115200"))
SYNC1 = 0xAA
SYNC2 = 0x55

# ===== MATRIX =====
W = H = 16
N = W * H
L = N * 3

# ===== AUDIO =====
SR = 44100
BLOCK = 1024
DEVICE = int(os.environ.get("AUDIO_DEV", "2"))  # HyperX = card 2

GAIN = 2.0          # reguluj czułość
SMOOTH = 0.6        # wygładzenie

def crc8(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

def rms(x):
    return float(np.sqrt(np.mean(x * x) + 1e-12))

def make_bars(level):
    buf = bytearray(L)
    h = int(level * 15)
    for x in range(16):
        for y in range(16):
            if 15 - y <= h:
                i = (y * 16 + x) * 3
                buf[i+0] = 0
                buf[i+1] = 200
                buf[i+2] = 40
    return buf

def main():
    print(f"[INFO] ESP {PORT} @ {BAUD}")
    print(f"[INFO] MIC dev={DEVICE} sr={SR}")

    ser = serial.Serial(PORT, BAUD, timeout=0)
    fid = 0
    level_sm = 0.0

    def audio_cb(indata, frames, time_info, status):
        nonlocal level_sm, fid
        x = indata[:, 0]
        r = rms(x) * GAIN
        r = min(1.0, r)

        level_sm = SMOOTH * level_sm + (1 - SMOOTH) * r
        payload = make_bars(level_sm)

        hdr = bytes([SYNC1, SYNC2, fid, L & 0xFF, (L >> 8) & 0xFF])
        pkt = hdr + payload + bytes([crc8(payload)])

        ser.write(pkt)
        fid = (fid + 1) & 0xFF

    with sd.InputStream(
        device=DEVICE,
        channels=1,
        samplerate=SR,
        blocksize=BLOCK,
        dtype="float32",
        callback=audio_cb,
    ):
        print("[RUN] mic → ESP (Ctrl+C to stop)")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
