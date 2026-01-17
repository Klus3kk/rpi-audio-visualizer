#!/usr/bin/env python3
import os, time, serial
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
SR = int(os.environ.get("AUDIO_SR", "44100"))
BLOCK = int(os.environ.get("AUDIO_BLOCK", "1024"))
AUDIO_DEV = int(os.environ.get("AUDIO_DEV", "0"))

# ===== TUNING =====
GAIN = float(os.environ.get("GAIN", "4.0"))          # czułość
SMOOTH = float(os.environ.get("SMOOTH", "0.65"))     # wygładzanie RMS 0..0.95
FPS = float(os.environ.get("FPS", "30"))

# Peak-hold behavior
PEAK_HOLD_MS = int(os.environ.get("PEAK_HOLD_MS", "140"))   # jak długo peak stoi
PEAK_FALL_PER_S = float(os.environ.get("PEAK_FALL_PER_S", "7.5"))  # ile pikseli/s opada peak

# Colors (RGB in payload; ESP maps to serpentine)
BAR_RGB  = (0, 160, 40)
PEAK_RGB = (220, 200, 40)   # żółtawy
BG_RGB   = (0, 0, 0)

def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x) + 1e-12))

def set_px(buf: bytearray, x: int, y: int, rgb):
    # row-major; ESP does serpentine in XY()
    i = (y * W + x) * 3
    buf[i+0] = rgb[0] & 0xFF
    buf[i+1] = rgb[1] & 0xFF
    buf[i+2] = rgb[2] & 0xFF

def make_frame(level_h: int, peak_y: int) -> bytes:
    """
    level_h: 0..15  (height of filled bar)
    peak_y : 0..15  (y coordinate of peak marker)
    y=15 bottom, y=0 top
    """
    buf = bytearray(L)
    # background already zeros

    for x in range(W):
        # bar
        for y in range(H):
            if (H - 1 - y) <= level_h:  # bottom-up fill
                set_px(buf, x, y, BAR_RGB)

        # peak marker: single pixel line
        py = max(0, min(H - 1, peak_y))
        set_px(buf, x, py, PEAK_RGB)

    return bytes(buf)

def main():
    print(f"[INFO] ESP {PORT} @ {BAUD}")
    print(f"[INFO] MIC dev={AUDIO_DEV} sr={SR} block={BLOCK}")
    print(f"[INFO] GAIN={GAIN} SMOOTH={SMOOTH} FPS={FPS}")
    print(f"[INFO] PEAK_HOLD_MS={PEAK_HOLD_MS} PEAK_FALL_PER_S={PEAK_FALL_PER_S}")

    ser = serial.Serial(PORT, BAUD, timeout=0)

    fid = 0
    level_sm = 0.0

    peak_level = 0.0          # peak as "height" (0..15)
    peak_hold_until = 0.0     # timestamp when peak starts to fall

    last_send = time.perf_counter()
    t0 = time.perf_counter()

    def send_frame(payload: bytes):
        nonlocal fid
        hdr = bytes([SYNC1, SYNC2, fid & 0xFF, L & 0xFF, (L >> 8) & 0xFF])
        pkt = hdr + payload + bytes([crc8(payload)])
        ser.write(pkt)
        fid = (fid + 1) & 0xFF

    def audio_cb(indata, frames, time_info, status):
        nonlocal level_sm, peak_level, peak_hold_until, last_send

        now = time.perf_counter()
        # throttle to FPS (callback can be faster)
        if (now - last_send) < (1.0 / FPS):
            return
        dt = now - last_send
        last_send = now

        x = indata[:, 0].astype(np.float32, copy=False)
        r = rms(x) * GAIN
        r = 0.0 if r < 0 else (1.0 if r > 1.0 else r)

        # smooth input level
        level_sm = (SMOOTH * level_sm) + ((1.0 - SMOOTH) * r)

        # current bar height
        cur_h = level_sm * 15.0

        # peak logic
        if cur_h >= peak_level:
            peak_level = cur_h
            peak_hold_until = now + (PEAK_HOLD_MS / 1000.0)
        else:
            if now >= peak_hold_until:
                peak_level = max(cur_h, peak_level - (PEAK_FALL_PER_S * dt))

        # convert to int heights
        level_h = int(round(cur_h))
        peak_h = int(round(peak_level))

        level_h = max(0, min(15, level_h))
        peak_h = max(0, min(15, peak_h))

        # map peak height to y coordinate (top=0 bottom=15)
        peak_y = (H - 1) - peak_h

        payload = make_frame(level_h=level_h, peak_y=peak_y)
        send_frame(payload)

    with sd.InputStream(
        device=AUDIO_DEV,
        channels=1,
        samplerate=SR,
        blocksize=BLOCK,
        dtype="float32",
        callback=audio_cb,
    ):
        print("[RUN] mic → peak-hold bars → ESP (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
