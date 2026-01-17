#!/usr/bin/env python3
import os, time, math, serial, select

PORT = os.environ.get("ESP_PORT", "/dev/ttyUSB0")
BAUD = int(os.environ.get("ESP_BAUD", "115200"))   # zacznij od 115200
W = H = 16
N = W * H
L = N * 3
SYNC1 = 0xAA
SYNC2 = 0x55

def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

def make_frame(t: float) -> bytes:
    buf = bytearray(L)
    for x in range(16):
        h = int((math.sin(t * 1.5 + x * 0.35) * 0.5 + 0.5) * 15)
        for y in range(16):
            if 15 - y <= h:
                i = (y * 16 + x) * 3
                buf[i + 0] = 0
                buf[i + 1] = 255
                buf[i + 2] = 40
    return bytes(buf)

def main():
    print(f"[INFO] port={PORT} baud={BAUD} frame={L}")
    ser = serial.Serial(PORT, BAUD, timeout=0)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    fid = 0
    t0 = time.time()
    last_stat = time.time()
    frames = 0
    acks = 0

    while True:
        t = time.time() - t0
        payload = make_frame(t)
        c = crc8(payload)
        hdr = bytes([SYNC1, SYNC2, fid & 0xFF, L & 0xFF, (L >> 8) & 0xFF])
        pkt = hdr + payload + bytes([c])

        ser.write(pkt)
        frames += 1
        fid = (fid + 1) & 0xFF

        # non-blocking read for ACK 0xCC (jeśli dodasz w ESP)
        r, _, _ = select.select([ser.fileno()], [], [], 0)
        if r:
            data = ser.read(1024)
            acks += data.count(b"\xCC")

        now = time.time()
        if now - last_stat >= 1.0:
            print(f"[STAT] fps={frames/(now-last_stat):.1f} acks={acks} last_crc=0x{c:02X}")
            frames = 0
            acks = 0
            last_stat = now

        time.sleep(1/30)

if __name__ == "__main__":
    main()
