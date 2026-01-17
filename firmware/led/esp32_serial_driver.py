import os
import threading
import serial
import time

SYNC1 = 0xAA
SYNC2 = 0x55

def _crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc

class EspSerialDriver:
    """
    Protokół zgodny z ESP32 receiver:
      AA 55 <frame_id> <len_lo> <len_hi> <payload RGB...> <crc8(payload)>
    Payload: row-major 16x16 (y*W + x), 768B.
    """
    def __init__(self, num_leds=256, port="/dev/ttyUSB0", baud=115200, debug=False):
        self.num_leds = int(num_leds)
        self.frame_len = self.num_leds * 3
        self.buf = bytearray(self.frame_len)
        self.lock = threading.Lock()
        self.frame_id = 0
        self.debug = bool(debug)

        self.port = port
        self.baud = int(baud)

        self.ser = serial.Serial(self.port, self.baud, timeout=0, write_timeout=1)
        # mała pauza po otwarciu, czasem pomaga na CH340
        time.sleep(0.08)

        if self.debug:
            print(f"[ESPDRV] open port={self.port} baud={self.baud} frame_len={self.frame_len}")

    def set_pixel(self, i, rgb):
        if i < 0 or i >= self.num_leds:
            return
        r, g, b = rgb
        j = i * 3
        with self.lock:
            self.buf[j]   = int(r) & 0xFF
            self.buf[j+1] = int(g) & 0xFF
            self.buf[j+2] = int(b) & 0xFF

    def fill(self, rgb):
        r, g, b = (int(rgb[0]) & 0xFF, int(rgb[1]) & 0xFF, int(rgb[2]) & 0xFF)
        row = bytes((r, g, b))
        with self.lock:
            for i in range(self.num_leds):
                j = i * 3
                self.buf[j:j+3] = row

    def show(self):
        with self.lock:
            payload = bytes(self.buf)

        fid = self.frame_id & 0xFF
        hdr = bytes([SYNC1, SYNC2, fid, self.frame_len & 0xFF, (self.frame_len >> 8) & 0xFF])
        pkt = hdr + payload + bytes([_crc8(payload)])

        n = self.ser.write(pkt)
        if self.debug and n != len(pkt):
            print(f"[ESPDRV] short write n={n} want={len(pkt)}")

        self.frame_id = (self.frame_id + 1) & 0xFF

    def clear(self):
        self.fill((0, 0, 0))
        self.show()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass
