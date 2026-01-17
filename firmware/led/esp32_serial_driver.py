import os
import threading
import serial

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

class Esp32SerialDriver:
    """
    Wysyła pełne ramki 16x16 do ESP32 po USB Serial.
    Protokół:
      AA 55 <frame_id> <len_lo> <len_hi> <payload 768B RGB> <crc8>
    Payload jest row-major (y*W + x), a ESP mapuje serpentine w XY().
    """
    def __init__(self, port="/dev/ttyUSB0", baud=921600, num_leds=256):
        self.num_leds = int(num_leds)
        self.frame_len = self.num_leds * 3  # 768
        self.buf = bytearray(self.frame_len)
        self.lock = threading.Lock()
        self.frame_id = 0

        self.port = port
        self.baud = int(baud)

        self.ser = serial.Serial(self.port, self.baud, timeout=0, write_timeout=1)

    def set_pixel(self, i, rgb):
        if i < 0 or i >= self.num_leds:
            return
        r, g, b = rgb
        with self.lock:
            j = i * 3
            self.buf[j + 0] = int(r) & 0xFF
            self.buf[j + 1] = int(g) & 0xFF
            self.buf[j + 2] = int(b) & 0xFF

    def fill(self, rgb):
        r, g, b = rgb
        r &= 0xFF; g &= 0xFF; b &= 0xFF
        with self.lock:
            for i in range(self.num_leds):
                j = i * 3
                self.buf[j:j+3] = bytes((r, g, b))

    def show(self):
        with self.lock:
            payload = bytes(self.buf)

        hdr = bytes([0xAA, 0x55, self.frame_id & 0xFF, self.frame_len & 0xFF, (self.frame_len >> 8) & 0xFF])
        pkt = hdr + payload + bytes([_crc8(payload)])

        self.ser.write(pkt)
        self.frame_id = (self.frame_id + 1) & 0xFF

    def clear(self):
        self.fill((0, 0, 0))
        self.show()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass
