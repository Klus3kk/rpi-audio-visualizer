# firmware/ui/lcd_st7789.py
# Minimal ST7789 SPI driver (no luma). Uses spidev + RPi.GPIO.
# Panel: 240x320. We render UI in landscape (320x240) and transpose() to panel.
#
# Pins (BCM):
#   DC  = 25
#   RST = 24
#   CS  = None if you use CE0/CE1 (recommended), otherwise set BCM pin (e.g. 5)
#
# SPI:
#   /dev/spidev0.0 => bus=0 dev=0
#   /dev/spidev0.1 => bus=0 dev=1

import time
import spidev
import RPi.GPIO as GPIO


class LcdSt7789:
    def __init__(
        self,
        *,
        width=240,
        height=320,
        spi_bus=0,
        spi_dev=0,
        spi_hz=40_000_000,
        dc=25,
        rst=24,
        cs=None,          # None => CE0/CE1 hardware CS
        invert=True,
        madctl=0x00,      # try 0x00; if colors/axes wrong, adjust later
    ):
        self.w = int(width)
        self.h = int(height)

        self.spi_bus = int(spi_bus)
        self.spi_dev = int(spi_dev)
        self.spi_hz = int(spi_hz)

        self.DC = int(dc)
        self.RST = int(rst)
        self.CS = None if cs is None else int(cs)

        self.invert = bool(invert)
        self.madctl = int(madctl) & 0xFF

        self._init_gpio()
        self._init_spi()
        self._init_panel()

    def _init_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.DC, GPIO.OUT)
        GPIO.setup(self.RST, GPIO.OUT)
        if self.CS is not None:
            GPIO.setup(self.CS, GPIO.OUT)
            GPIO.output(self.CS, 1)

    def _init_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(self.spi_bus, self.spi_dev)
        self.spi.max_speed_hz = self.spi_hz
        self.spi.mode = 0

    def _cs_low(self):
        if self.CS is not None:
            GPIO.output(self.CS, 0)

    def _cs_high(self):
        if self.CS is not None:
            GPIO.output(self.CS, 1)

    def _cmd(self, c):
        GPIO.output(self.DC, 0)
        self._cs_low()
        self.spi.writebytes([int(c) & 0xFF])
        self._cs_high()

    def _data(self, buf):
        GPIO.output(self.DC, 1)
        self._cs_low()
        self.spi.writebytes(list(buf))
        self._cs_high()

    def _reset(self):
        GPIO.output(self.RST, 1)
        time.sleep(0.05)
        GPIO.output(self.RST, 0)
        time.sleep(0.05)
        GPIO.output(self.RST, 1)
        time.sleep(0.12)

    def _init_panel(self):
        self._reset()

        self._cmd(0x01)  # SWRESET
        time.sleep(0.12)
        self._cmd(0x11)  # SLPOUT
        time.sleep(0.12)

        self._cmd(0x3A)  # COLMOD
        self._data([0x55])  # 16-bit color

        self._cmd(0x36)  # MADCTL
        self._data([self.madctl])

        if self.invert:
            self._cmd(0x21)  # INVON
            time.sleep(0.01)

        self._cmd(0x29)  # DISPON
        time.sleep(0.12)

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)  # CASET
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])

        self._cmd(0x2B)  # RASET
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])

        self._cmd(0x2C)  # RAMWR

    @staticmethod
    def _rgb565_bytes(img_rgb, W, H):
        # img_rgb: PIL.Image RGB size (W,H)
        px = img_rgb.load()
        out = bytearray(W * H * 2)
        i = 0
        for y in range(H):
            for x in range(W):
                r, g, b = px[x, y]
                v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                out[i] = (v >> 8) & 0xFF
                out[i + 1] = v & 0xFF
                i += 2
        return out

    def display(self, img_rgb):
        # full frame
        self._set_window(0, 0, self.w - 1, self.h - 1)
        buf = self._rgb565_bytes(img_rgb, self.w, self.h)

        GPIO.output(self.DC, 1)
        self._cs_low()
        chunk = 4096
        for i in range(0, len(buf), chunk):
            self.spi.writebytes(buf[i : i + chunk])
        self._cs_high()

    def close(self):
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            GPIO.cleanup()
        except Exception:
            pass
