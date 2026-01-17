#!/usr/bin/env python3
import os
import time
import serial

PORT = os.environ.get("ESP_PORT", "/dev/ttyUSB0")
BAUD = int(os.environ.get("ESP_BAUD", "921600"))

NUM_LEDS = 256
FRAME_LEN = NUM_LEDS * 3  # 768

def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc

def send_frame(ser, payload: bytes, frame_id: int = 0):
    hdr = bytes([0xAA, 0x55, frame_id & 0xFF, FRAME_LEN & 0xFF, (FRAME_LEN >> 8) & 0xFF])
    ser.write(hdr + payload + bytes([crc8(payload)]))

def solid(r, g, b):
    return bytes([r, g, b]) * NUM_LEDS

def main():
    print(f"[INFO] opening {PORT} @ {BAUD}")
    ser = serial.Serial(PORT, BAUD, timeout=0, write_timeout=1)
    try:
        seq = [
            ("RED",   solid(255, 0, 0)),
            ("GREEN", solid(0, 255, 0)),
            ("BLUE",  solid(0, 0, 255)),
            ("WHITE", solid(255, 255, 255)),
            ("OFF",   solid(0, 0, 0)),
        ]
        fid = 0
        for name, payload in seq:
            print("[SEND]", name)
            send_frame(ser, payload, frame_id=fid)
            fid = (fid + 1) & 0xFF
            time.sleep(1.0)
    finally:
        ser.close()
        print("[DONE]")

if __name__ == "__main__":
    main()
