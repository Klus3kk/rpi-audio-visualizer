#!/usr/bin/env python3
import os, time, serial
import numpy as np
import sounddevice as sd

# ===== Serial / protocol =====
PORT = os.environ.get("ESP_PORT", "/dev/ttyUSB0")
BAUD = int(os.environ.get("ESP_BAUD", "115200"))
SYNC1, SYNC2 = 0xAA, 0x55

W = H = 16
N = W * H
L = N * 3

# ===== Audio =====
SR = int(os.environ.get("AUDIO_SR", "44100"))
BLOCK = int(os.environ.get("AUDIO_BLOCK", "1024"))
DEV = int(os.environ.get("AUDIO_DEV", "0"))

# ===== Tuning =====
GAIN = float(os.environ.get("GAIN", "2.5"))
SMOOTH = float(os.environ.get("SMOOTH", "0.65"))       # smoothing of band levels
FPS = float(os.environ.get("FPS", "35"))
BRI = float(os.environ.get("BRI", "0.35"))             # global brightness scaling 0..1
NOISE_FLOOR = float(os.environ.get("NOISE", "0.02"))   # small noise gate

# ===== Colors =====
# (R,G,B) in payload; ESP maps serpentine internally
BASE = np.array([0, 170, 40], dtype=np.float32)        # green
PEAK = np.array([220, 200, 40], dtype=np.float32)      # yellow peak

def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

def set_px(buf: bytearray, x: int, y: int, rgb):
    i = (y * W + x) * 3
    buf[i+0] = int(rgb[0]) & 0xFF
    buf[i+1] = int(rgb[1]) & 0xFF
    buf[i+2] = int(rgb[2]) & 0xFF

def main():
    print(f"[INFO] ESP {PORT} @ {BAUD}")
    print(f"[INFO] MIC dev={DEV} sr={SR} block={BLOCK}")
    print(f"[INFO] GAIN={GAIN} SMOOTH={SMOOTH} FPS={FPS} BRI={BRI} NOISE={NOISE_FLOOR}")

    ser = serial.Serial(PORT, BAUD, timeout=0)
    fid = 0

    win = np.hanning(BLOCK).astype(np.float32)

    # 16 pasm logarytmicznych
    fmin, fmax = 60.0, 16000.0
    edges = np.geomspace(fmin, fmax, num=16+1)

    def hz_to_bin(hz):
        return int(np.floor((hz / (SR/2.0)) * (BLOCK//2)))

    bands = []
    for i in range(16):
        lo = max(1, hz_to_bin(edges[i]))
        hi = max(lo+1, hz_to_bin(edges[i+1]))
        bands.append((lo, hi))

    level = np.zeros(16, dtype=np.float32)
    peak = np.zeros(16, dtype=np.float32)

    last_send = time.perf_counter()

    def send(payload: bytes):
        nonlocal fid
        hdr = bytes([SYNC1, SYNC2, fid & 0xFF, L & 0xFF, (L >> 8) & 0xFF])
        pkt = hdr + payload + bytes([crc8(payload)])
        ser.write(pkt)
        fid = (fid + 1) & 0xFF

    def audio_cb(indata, frames, tinfo, status):
        nonlocal last_send, level, peak
        now = time.perf_counter()
        if (now - last_send) < (1.0 / FPS):
            return
        dt = now - last_send
        last_send = now

        x = indata[:,0].astype(np.float32, copy=False) * GAIN

        # noise gate
        rms = float(np.sqrt(np.mean(x*x) + 1e-12))
        if rms < NOISE_FLOOR:
            x *= 0.0

        xw = x * win
        spec = np.fft.rfft(xw)
        mag = np.abs(spec).astype(np.float32)
        mag[0] = 0.0
        mag = np.log1p(mag)  # compress dynamic range

        raw = np.zeros(16, dtype=np.float32)
        for i,(lo,hi) in enumerate(bands):
            raw[i] = float(np.mean(mag[lo:hi])) if hi > lo else 0.0

        # normalize per-frame
        mn, mx = float(raw.min()), float(raw.max())
        if mx - mn < 1e-6:
            raw[:] = 0.0
        else:
            raw = (raw - mn) / (mx - mn)

        # smooth
        level = (SMOOTH * level) + ((1.0 - SMOOTH) * raw)

        # peak-hold simple
        fall = 2.8 * dt
        peak = np.maximum(level, peak - fall)

        # build frame
        buf = bytearray(L)
        for xcol in range(16):
            h = int(level[xcol] * 15.0 + 0.5)
            h = max(0, min(15, h))

            # bar (bottom-up)
            for y in range(15, 15 - h, -1):
                c = BASE * BRI
                set_px(buf, xcol, y, c)

            # peak pixel
            ph = int(peak[xcol] * 15.0 + 0.5)
            ph = max(0, min(15, ph))
            py = 15 - ph
            cpk = PEAK * BRI
            set_px(buf, xcol, py, cpk)

        send(bytes(buf))

    with sd.InputStream(device=DEV, channels=1, samplerate=SR, blocksize=BLOCK,
                        dtype="float32", callback=audio_cb):
        print("[RUN] FFT bars → ESP (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
