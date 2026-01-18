# firmware/ui/lcd_st7789.py
import time
import spidev
import numpy as np
from PIL import Image

class _GPIO:
    """
    Minimalny wrapper na lgpio (bez RPi.GPIO).
    """
    def __init__(self):
        import lgpio  # wymagane
        self.lgpio = lgpio
        self.h = lgpio.gpiochip_open(0)

    def setup_out(self, pin: int, initial: int = 0):
        self.lgpio.gpio_claim_output(self.h, pin, initial)

    def write(self, pin: int, value: int):
        self.lgpio.gpio_write(self.h, pin, 1 if value else 0)

    def close(self):
        try:
            self.lgpio.gpiochip_close(self.h)
        except Exception:
            pass


def _rgb888_to_rgb565be_bytes(img: Image.Image) -> bytes:
    """
    PIL RGB -> RGB565 big-endian bytes, szybkie (numpy).
    """
    arr = np.asarray(img.convert("RGB"), dtype=np.uint8)  # (H,W,3)
    r = arr[..., 0].astype(np.uint16)
    g = arr[..., 1].astype(np.uint16)
    b = arr[..., 2].astype(np.uint16)
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)  # RGB565
    # big-endian:
    v = v.byteswap()
    return v.tobytes()


class LcdSt7789:
    """
    ST7789 SPI (240x320 typowo), z renderem poziomym 320x240.

    - SPI: /dev/spidev<bus>.<dev>
    - DC, RST: GPIO BCM
    - CS: używamy sprzętowego CS z spidev (nie ręczny GPIO CS)
    """
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
        rotate=90,          # 0/90/180/270
        invert=True,        # bardzo często True dla ST7789
        madctl_base=0x00,   # bazowy MADCTL
    ):
        self.panel_w = int(width)
        self.panel_h = int(height)

        # UI będzie poziomo: 320x240
        # Jeśli panel jest 240x320, to poziomo to 320x240
        self.W = int(height) if rotate in (90, 270) else int(width)
        self.H = int(width)  if rotate in (90, 270) else int(height)

        self.dc = int(dc)
        self.rst = int(rst)
        self.rotate = int(rotate)
        self.invert = bool(invert)
        self.madctl_base = int(madctl_base) & 0xFF

        self.gpio = _GPIO()
        self.gpio.setup_out(self.dc, 0)
        self.gpio.setup_out(self.rst, 1)

        self.spi = spidev.SpiDev()
        self.spi.open(int(spi_bus), int(spi_dev))
        self.spi.max_speed_hz = int(spi_hz)
        self.spi.mode = 0

        self._init_panel()

    def close(self):
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            self.gpio.close()
        except Exception:
            pass

    # --- low-level ---
    def _cmd(self, c: int):
        self.gpio.write(self.dc, 0)
        self.spi.writebytes([c & 0xFF])

    def _data(self, data):
        self.gpio.write(self.dc, 1)
        if isinstance(data, (bytes, bytearray)):
            # chunkowanie żeby nie dusić writebytes
            chunk = 4096
            for i in range(0, len(data), chunk):
                self.spi.writebytes(data[i:i+chunk])
        else:
            self.spi.writebytes([int(x) & 0xFF for x in data])

    def _reset(self):
        self.gpio.write(self.rst, 1)
        time.sleep(0.02)
        self.gpio.write(self.rst, 0)
        time.sleep(0.05)
        self.gpio.write(self.rst, 1)
        time.sleep(0.12)

    def _madctl_for_rotate(self) -> int:
        # MADCTL bits: MY(0x80), MX(0x40), MV(0x20), RGB/BGR(0x08)
        # Najbezpieczniejsze warianty dla ST7789:
        r = self.rotate % 360
        if r == 0:
            rot = 0x00
        elif r == 90:
            rot = 0x60  # MV|MX
        elif r == 180:
            rot = 0xC0  # MY|MX
        elif r == 270:
            rot = 0xA0  # MV|MY
        else:
            rot = 0x00
        return (self.madctl_base ^ rot) & 0xFF

    def _init_panel(self):
        self._reset()

        self._cmd(0x01)  # SWRESET
        time.sleep(0.12)

        self._cmd(0x11)  # SLPOUT
        time.sleep(0.12)

        self._cmd(0x3A)  # COLMOD
        self._data([0x55])  # 16-bit

        self._cmd(0x36)  # MADCTL
        self._data([self._madctl_for_rotate()])

        if self.invert:
            self._cmd(0x21)  # INVON
        else:
            self._cmd(0x20)  # INVOFF
        time.sleep(0.01)

        self._cmd(0x29)  # DISPON
        time.sleep(0.12)

        # czyść na czarno na start
        self.clear()

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)  # CASET
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])

        self._cmd(0x2B)  # RASET
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])

        self._cmd(0x2C)  # RAMWR

    # --- high-level ---
    def clear(self):
        img = Image.new("RGB", (self.W, self.H), (0, 0, 0))
        self.display(img)

    def display(self, img: Image.Image):
        if img.size != (self.W, self.H):
            img = img.resize((self.W, self.H))
        self._set_window(0, 0, self.W - 1, self.H - 1)
        buf = _rgb888_to_rgb565be_bytes(img)
        self._data(buf)
