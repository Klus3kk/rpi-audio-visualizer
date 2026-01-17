#!/usr/bin/env python3
import os
import sys
import time
import math
import struct
import serial

PORT = os.environ.get("ESP_PORT", "/dev/ttyUSB0")
BAUD = int(os.environ.get("ESP_BAUD", "115200"))  # zmień na 921600 jak będzie stabilnie

W, H = 16, 16
N = W * H
FRAME_LEN = N * 3  # 768

SYNC1 = 0xAA
SYNC2 = 0x55

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

def make_dot_frame(t: float) -> bytes:
    # ciemne tło + jedna jasna kropka, żeby było widać mapowanie
    buf = bytearray(FRAME_LEN)

    # tło
    for i in range(0, FRAME_LEN, 3):
        buf[i+0] = 0
        buf[i+1] = 0
        buf[i+2] = 0

    # kropka
    x = int((math.sin(t * 1.2) * 0.5 + 0.5) * (W - 1))
    y = int((math.cos(t * 0.9) * 0.5 + 0.5) * (H - 1))

    idx = (y * W + x) * 3  # row-major (ESP mapuje serpentine w XY)
    buf[idx+0] = 255
    buf[idx+1] = 60
    buf[idx+2] = 10

    return bytes(buf)