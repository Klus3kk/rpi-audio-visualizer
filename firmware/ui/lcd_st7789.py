# firmware/ui/lcd_st7789.py
import time
import spidev
import lgpio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ST7789 commands
_SWRESET = 0x01
_SLPOUT  = 0x11
_COLMOD  = 0x3A
_MADCTL  = 0x36
_INVON   = 0x21
_DISPON  = 0x29
_CASET   = 0x2A
_RASET   = 0x2B
_RAMWR   = 0x2C

# MADCTL bits (common)
_MX = 0x40
_MY = 0x80
_MV = 0x20
_RGB = 0x00  # RGB order (często OK; jak kolory złe -> spróbuj 0x08 BGR)


class LcdSt7789:
    """
    Minimalny ST7789: spidev + lgpio (bez RPi.GPIO i bez luma).
    - Czarny background
    - rotate 0/90/180/270
    - szybka konwersja RGB888 -> RGB565 (numpy)
    """

    def __init__(
        self,
        width=240,
        height=320,
        spi_bus=0,
        spi_dev=0,
        spi_hz=40_000_000,
        dc=25,
        rst=24,
        cs_gpio=None,     # jak używasz CE0/CE1, zostaw None
        rotate=90,
        invert=True,
        madctl_rgb=True,  # True => RGB, False => BGR
    ):
        self.panel_w = int(width)
        self.panel_h = int(height)
        self.rotate = int(rotate)

        # wyjściowy rozmiar “ekranu logicznego” po rotacji
        if self.rotate in (90, 270):
            self.w, self.h = self.panel_h, self.panel_w
        else:
            self.w, self.h = self.panel_w, self.panel_h

        self.dc = int(dc)
        self.rst = int(rst)
        self.cs_gpio = None if cs_gpio is None else int(cs_gpio)
        self.spi_hz = int(spi_hz)

        # lgpio chip
        self.gpio = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self.gpio, self.dc, 0)
        lgpio.gpio_claim_output(self.gpio, self.rst, 1)
        if self.cs_gpio is not None:
            lgpio.gpio_claim_output(self.gpio, self.cs_gpio, 1)

        # SPI
        self.spi = spidev.SpiDev()
        self.spi.open(int(spi_bus), int(spi_dev))
        self.spi.max_speed_hz = self.spi_hz
        self.spi.mode = 0

        self._madctl_rgb = _RGB if madctl_rgb else 0x08  # BGR=0x08
        self._init_panel(invert=bool(invert))

        # font
        self.font = ImageFont.load_default()

    # -------- low-level --------
    def _cs(self, v: int):
        if self.cs_gpio is not None:
            lgpio.gpio_write(self.gpio, self.cs_gpio, 1 if v else 0)

    def _dc(self, v: int):
        lgpio.gpio_write(self.gpio, self.dc, 1 if v else 0)

    def _rst_pulse(self):
        lgpio.gpio_write(self.gpio, self.rst, 1)
        time.sleep(0.05)
        lgpio.gpio_write(self.gpio, self.rst, 0)
        time.sleep(0.05)
        lgpio.gpio_write(self.gpio, self.rst, 1)
        time.sleep(0.12)

    def _cmd(self, c: int):
        self._dc(0)
        self._cs(0)
        self.spi.writebytes([c & 0xFF])
        self._cs(1)

    def _data(self, buf):
        self._dc(1)
        self._cs(0)
        self.spi.writebytes(buf)
        self._cs(1)

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(_CASET)
        self._data([(x0 >> 8) & 0xFF, x0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF])
        self._cmd(_RASET)
        self._data([(y0 >> 8) & 0xFF, y0 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF])
        self._cmd(_RAMWR)

    def _madctl_for_rotate(self):
        # Typowe mapowania dla ST7789; jeśli obraz jest “dziwnie”, zmienimy MADCTL.
        r = self.rotate % 360
        if r == 0:
            return self._madctl_rgb | _MX | _MY
        if r == 90:
            return self._madctl_rgb | _MV | _MY
        if r == 180:
            return self._madctl_rgb
        if r == 270:
            return self._madctl_rgb | _MV | _MX
        return self._madctl_rgb | _MV | _MY

    def _init_panel(self, invert: bool):
        self._rst_pulse()

        self._cmd(_SWRESET)
        time.sleep(0.12)
        self._cmd(_SLPOUT)
        time.sleep(0.12)

        self._cmd(_COLMOD)
        self._data([0x55])  # 16-bit

        self._cmd(_MADCTL)
        self._data([self._madctl_for_rotate()])

        if invert:
            self._cmd(_INVON)
            time.sleep(0.01)

        self._cmd(_DISPON)
        time.sleep(0.12)

        self.fill((0, 0, 0))

    # -------- drawing --------
    @staticmethod
    def _rgb888_to_rgb565_bytes(img: Image.Image) -> bytes:
        a = np.asarray(img.convert("RGB"), dtype=np.uint8)  # (h,w,3)
        r = a[:, :, 0].astype(np.uint16)
        g = a[:, :, 1].astype(np.uint16)
        b = a[:, :, 2].astype(np.uint16)
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)  # uint16 (h,w)
        out = np.empty((v.size * 2,), dtype=np.uint8)
        out[0::2] = (v.reshape(-1) >> 8).astype(np.uint8)
        out[1::2] = (v.reshape(-1) & 0xFF).astype(np.uint8)
        return out.tobytes()

    def display(self, img: Image.Image):
        # img MUSI mieć (self.w, self.h)
        if img.size != (self.w, self.h):
            img = img.resize((self.w, self.h))

        # wysyłamy zawsze do panelowego okna (0..panel_w-1, 0..panel_h-1)
        # bo MADCTL załatwia rotację
        self._set_window(0, 0, self.panel_w - 1, self.panel_h - 1)
        buf = self._rgb888_to_rgb565_bytes(img)

        self._dc(1)
        self._cs(0)
        # chunking
        chunk = 4096
        for i in range(0, len(buf), chunk):
            self.spi.writebytes(buf[i:i + chunk])
        self._cs(1)

    def fill(self, rgb=(0, 0, 0)):
        img = Image.new("RGB", (self.w, self.h), tuple(rgb))
        self.display(img)

    def close(self):
        try:
            self.fill((0, 0, 0))
        except Exception:
            pass
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            lgpio.gpiochip_close(self.gpio)
        except Exception:
            pass
