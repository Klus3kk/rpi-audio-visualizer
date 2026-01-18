# firmware/ui/lcd_st7789.py
import time
import spidev
import numpy as np
from PIL import Image

try:
    import RPi.GPIO as GPIO
except Exception as e:
    GPIO = None


class LcdSt7789:
    """
    ST7789 SPI driver (RGB565).
    Obsługa:
      - rotate: 0 / 90 / 180 / 270 (logiczny rozmiar w/h zmienia się przy 90/270)
      - CS na GPIO (software CS): cs=<BCM pin> + spidev.no_cs=True
      - invert: True/False
    """

    # ST7789 commands
    _SWRESET = 0x01
    _SLPOUT  = 0x11
    _COLMOD  = 0x3A
    _MADCTL  = 0x36
    _INVON   = 0x21
    _INVOFF  = 0x20
    _DISPON  = 0x29
    _CASET   = 0x2A
    _RASET   = 0x2B
    _RAMWR   = 0x2C

    def __init__(
        self,
        *,
        width=240,
        height=320,
        spi_bus=0,
        spi_dev=0,
        spi_hz=24_000_000,
        dc=25,
        rst=24,
        cs=5,              # GPIO CS (BCM) ; ustaw None jeśli masz CE0/CE1
        invert=True,
        rotate=90,         # 90 => landscape (320x240) dla panelu 240x320
        madctl_base=0x00,  # jeśli chcesz ręcznie, zostaw 0x00 i użyj rotate
    ):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO nie jest dostępne. Uruchamiasz to na RPi?")

        self.panel_w = int(width)
        self.panel_h = int(height)

        self.spi_bus = int(spi_bus)
        self.spi_dev = int(spi_dev)
        self.spi_hz  = int(spi_hz)

        self.DC  = int(dc)
        self.RST = int(rst)
        self.CS  = None if cs is None else int(cs)

        self.invert = bool(invert)
        self.rotate = int(rotate)
        self.madctl_base = int(madctl_base) & 0xFF

        # logical width/height after rotation
        if self.rotate in (90, 270):
            self.w = self.panel_h
            self.h = self.panel_w
        else:
            self.w = self.panel_w
            self.h = self.panel_h

        self._init_gpio()
        self._init_spi()
        self._init_lcd()

    # ---------- GPIO / SPI ----------

    def _init_gpio(self):
        # NOTE:
        # Jeśli dostajesz "Cannot determine SOC peripheral base address",
        # to uruchom ten program na RPi, i/lub:
        #   sudo usermod -aG gpio,spi pi
        #   (logout/login) albo uruchom test jako sudo.
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

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

        # jeśli CS jest na GPIO -> wyłącz HW CS w spidev
        if self.CS is not None:
            try:
                self.spi.no_cs = True
            except Exception:
                pass

    def _cs_low(self):
        if self.CS is not None:
            GPIO.output(self.CS, 0)

    def _cs_high(self):
        if self.CS is not None:
            GPIO.output(self.CS, 1)

    def _write(self, dc_level, data):
        GPIO.output(self.DC, 1 if dc_level else 0)
        self._cs_low()
        if isinstance(data, (bytes, bytearray, memoryview)):
            self.spi.writebytes2(data)
        else:
            self.spi.writebytes(data)
        self._cs_high()

    def _cmd(self, c):
        self._write(0, [int(c) & 0xFF])

    def _data(self, buf):
        self._write(1, buf)

    # ---------- LCD init ----------

    def _reset(self):
        GPIO.output(self.RST, 1)
        time.sleep(0.05)
        GPIO.output(self.RST, 0)
        time.sleep(0.05)
        GPIO.output(self.RST, 1)
        time.sleep(0.12)

    def _madctl_for_rotate(self):
        # ST7789: MADCTL bits:
        # MY 0x80, MX 0x40, MV 0x20, ML 0x10, RGB 0x00/BGR 0x08
        # Tu zakładamy RGB. Jeśli kolory są złe, dodaj 0x08.
        base = self.madctl_base & 0x1F  # zachowaj ewentualne BGR/ML
        r = self.rotate % 360
        if r == 0:
            return base | 0x00
        if r == 90:
            return base | 0x60  # MV|MX
        if r == 180:
            return base | 0xC0  # MX|MY
        if r == 270:
            return base | 0xA0  # MV|MY
        return base | 0x60

    def _init_lcd(self):
        self._reset()

        self._cmd(self._SWRESET)
        time.sleep(0.12)

        self._cmd(self._SLPOUT)
        time.sleep(0.12)

        # 16-bit RGB565
        self._cmd(self._COLMOD)
        self._data([0x55])
        time.sleep(0.01)

        # rotation
        self._cmd(self._MADCTL)
        self._data([self._madctl_for_rotate()])
        time.sleep(0.01)

        # inversion (często potrzebne dla ST7789 modułów)
        self._cmd(self._INVON if self.invert else self._INVOFF)
        time.sleep(0.01)

        self._cmd(self._DISPON)
        time.sleep(0.12)

    # ---------- Drawing ----------

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(self._CASET)
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])

        self._cmd(self._RASET)
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])

        self._cmd(self._RAMWR)

    @staticmethod
    def _rgb565_bytes(img: Image.Image, w: int, h: int) -> bytes:
        # szybka konwersja: RGB888 -> RGB565 big-endian
        if img.size != (w, h):
            img = img.resize((w, h), Image.NEAREST)
        img = img.convert("RGB")

        a = np.frombuffer(img.tobytes(), dtype=np.uint8).reshape((h, w, 3))
        r = a[:, :, 0].astype(np.uint16)
        g = a[:, :, 1].astype(np.uint16)
        b = a[:, :, 2].astype(np.uint16)
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        v = v.byteswap()  # big-endian
        return v.tobytes()

    def display(self, img: Image.Image):
        # pełny ekran
        self._set_window(0, 0, self.w - 1, self.h - 1)
        buf = self._rgb565_bytes(img, self.w, self.h)

        GPIO.output(self.DC, 1)
        self._cs_low()
        mv = memoryview(buf)
        chunk = 4096
        for i in range(0, len(buf), chunk):
            self.spi.writebytes2(mv[i:i + chunk])
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
