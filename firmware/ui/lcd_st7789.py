# firmware/ui/lcd_st7789.py
import time
import spidev
import lgpio
from PIL import Image
import numpy as np

class LcdSt7789:
    """
    Minimalny ST7789 SPI driver:
    - spidev do SPI
    - lgpio do DC/RST (+ opcjonalnie BL i ręczny CS)
    - rotate=90 => landscape (logical 320x240 na panel 240x320)
    """

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
        bl=None,          # np. 23 jeśli masz BL na GPIO; None jeśli BL na stałe do 3V3
        cs_gpio=None,     # np. 5 jeśli masz CS ręcznie na GPIO; None jeśli używasz CE0/CE1
        rotate=90,        # 0/90/180/270
        invert=True,
        madctl_base=0x00,
    ):
        self.panel_w = int(width)
        self.panel_h = int(height)
        self.rotate = int(rotate) % 360
        self.invert = bool(invert)
        self.madctl_base = int(madctl_base) & 0xFF

        self.DC = int(dc)
        self.RST = int(rst)
        self.BL = None if bl is None else int(bl)
        self.CS = None if cs_gpio is None else int(cs_gpio)

        # logical size (to co rysujesz w PIL)
        if self.rotate in (90, 270):
            self.W = self.panel_h
            self.H = self.panel_w
        else:
            self.W = self.panel_w
            self.H = self.panel_h

        # GPIO chip
        self.gpio = lgpio.gpiochip_open(0)

        lgpio.gpio_claim_output(self.gpio, self.DC, 0)
        lgpio.gpio_claim_output(self.gpio, self.RST, 1)

        if self.BL is not None:
            lgpio.gpio_claim_output(self.gpio, self.BL, 1)  # backlight ON

        if self.CS is not None:
            lgpio.gpio_claim_output(self.gpio, self.CS, 1)  # idle high

        # SPI
        self.spi = spidev.SpiDev()
        self.spi.open(int(spi_bus), int(spi_dev))
        self.spi.max_speed_hz = int(spi_hz)
        self.spi.mode = 0
        if self.CS is not None:
            self.spi.no_cs = True


        # init
        self._reset()
        self._init_panel()

    def close(self):
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            lgpio.gpiochip_close(self.gpio)
        except Exception:
            pass

    def _cs_low(self):
        if self.CS is not None:
            lgpio.gpio_write(self.gpio, self.CS, 0)

    def _cs_high(self):
        if self.CS is not None:
            lgpio.gpio_write(self.gpio, self.CS, 1)

    def _dc_cmd(self):
        lgpio.gpio_write(self.gpio, self.DC, 0)

    def _dc_data(self):
        lgpio.gpio_write(self.gpio, self.DC, 1)

    def _write(self, data: bytes):
        self._cs_low()
        CH = 4096
        for i in range(0, len(data), CH):
            chunk = data[i:i+CH]
            # writebytes2 przyjmuje bytes/bytearray bez konwersji
            self.spi.writebytes2(chunk)
        self._cs_high()


    def _cmd(self, c: int):
        self._dc_cmd()
        self._write(bytes([c & 0xFF]))

    def _data(self, b: bytes):
        if not b:
            return
        self._dc_data()
        self._write(b)

    def _reset(self):
        lgpio.gpio_write(self.gpio, self.RST, 1)
        time.sleep(0.02)
        lgpio.gpio_write(self.gpio, self.RST, 0)
        time.sleep(0.05)
        lgpio.gpio_write(self.gpio, self.RST, 1)
        time.sleep(0.12)

    def _madctl_value(self) -> int:
        # Najczęściej wymagane na ST7789: BGR=0x08
        # Bez rotacji w MADCTL (rotację robimy w software).
        mad = 0x08  # BGR
        return (mad ^ self.madctl_base) & 0xFF


    def _init_panel(self):
        self._cmd(0x01)   # SWRESET
        time.sleep(0.12)
        self._cmd(0x11)   # SLPOUT
        time.sleep(0.12)

        self._cmd(0x3A)   # COLMOD
        self._data(bytes([0x55]))  # 16-bit

        self._cmd(0x36)   # MADCTL
        self._data(bytes([self._madctl_value()]))

        if self.invert:
            self._cmd(0x21)  # INVON
        else:
            self._cmd(0x20)  # INVOFF

        self._cmd(0x29)   # DISPON
        time.sleep(0.12)

        # wyczyść na czarno
        self.fill((0, 0, 0))

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)  # CASET
        self._data(bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._cmd(0x2B)  # RASET
        self._data(bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        self._cmd(0x2C)  # RAMWR

    @staticmethod
    def _rgb888_to_rgb565_bytes(img_rgb: Image.Image) -> bytes:
        # szybka konwersja przez numpy
        a = np.asarray(img_rgb, dtype=np.uint8)
        r = a[..., 0].astype(np.uint16)
        g = a[..., 1].astype(np.uint16)
        b = a[..., 2].astype(np.uint16)
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out = np.empty((v.size * 2,), dtype=np.uint8)
        out[0::2] = (v >> 8).astype(np.uint8)
        out[1::2] = (v & 0xFF).astype(np.uint8)
        return out.tobytes()

    def display(self, img: Image.Image):
        # img musi mieć logical W x H
        if img.size != (self.W, self.H):
            img = img.resize((self.W, self.H))

        img = img.convert("RGB")

        # panel zawsze ma 240x320 okno RAM — przy rotate=90/270 my tylko zmieniamy MADCTL
        # więc wysyłamy zawsze pełne panel_w x panel_h w naturalnym układzie:
        if self.rotate == 90:
            img2 = img.rotate(90, expand=True)
        elif self.rotate == 270:
            img2 = img.rotate(-90, expand=True)  # albo 270
        elif self.rotate == 180:
            img2 = img.rotate(180, expand=False)
        else:
            img2 = img


        if img2.size != (self.panel_w, self.panel_h):
            img2 = img2.resize((self.panel_w, self.panel_h))

        self._set_window(0, 0, self.panel_w - 1, self.panel_h - 1)
        buf = self._rgb888_to_rgb565_bytes(img2)
        self._dc_data()
        self._write(buf)

    def fill(self, rgb):
        img = Image.new("RGB", (self.W, self.H), rgb)
        self.display(img)
