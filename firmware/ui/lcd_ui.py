# firmware/ui/lcd_ui.py
import math
from PIL import Image, ImageDraw, ImageFont
from firmware.ui.lcd_st7789 import LcdSt7789

NEON = (0, 200, 255)
NEON_D = (0, 90, 120)
BG = (0, 0, 0)

def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

class LCDUI:
    """
    Minimal UI:
    - 2 tryby: MIC / BT
    - czarne tło, neon
    - proste prostokąty (nokia-ish), bez zaokrągleń
    """

    def __init__(
        self,
        *,
        dc: int,
        rst: int,
        cs: int | None = None,       # jeśli CE0/CE1 -> None
        spi_bus: int = 0,
        spi_dev: int = 0,
        spi_hz: int = 24_000_000,
        rotate: int = 90,
        dim: float = 1.0,           # mnożnik koloru UI (0..1)
        invert: bool = True,
        madctl_base: int = 0x00,
        width: int = 240,
        height: int = 320,
    ):
        self.dim = _clamp01(float(dim))

        self.lcd = LcdSt7789(
            width=width,
            height=height,
            spi_bus=spi_bus,
            spi_dev=spi_dev,
            spi_hz=spi_hz,
            dc=dc,
            rst=rst,
            cs_gpio=cs,
            rotate=rotate,
            invert=invert,
            madctl_base=madctl_base,
        )

        # logical size (to rysujesz w PIL)
        self.W = self.lcd.W
        self.H = self.lcd.H

        self.font = ImageFont.load_default()

        self._mode = "mic"
        self._status = ""
        self._level = 0.0
        self._bt_connected = False
        self._effect = "bars"

    def close(self):
        self.lcd.close()

    # ----- setters -----
    def set_mode(self, mode: str):
        mode = (mode or "mic").lower()
        self._mode = "bt" if mode == "bt" else "mic"

    def set_status(self, text: str):
        self._status = (text or "")[:28]

    def set_level(self, v: float):
        self._level = _clamp01(float(v))

    def set_bt(self, *, connected: bool, name: str = ""):
        self._bt_connected = bool(connected)
        self._bt_name = (name or "")[:18]

    def set_effect(self, name: str):
        self._effect = (name or "")[:14]

    # ----- render -----
    def render(self):
        img = Image.new("RGB", (self.W, self.H), BG)
        d = ImageDraw.Draw(img)

        neon = tuple(int(c * self.dim) for c in NEON)
        neon_d = tuple(int(c * self.dim) for c in NEON_D)

        # header box
        d.rectangle([4, 4, self.W - 5, 34], outline=neon_d)
        d.text((10, 12), "VISUALIZER", font=self.font, fill=neon)

        # mode tabs
        left = [4, 40, self.W // 2 - 2, 70]
        right = [self.W // 2 + 1, 40, self.W - 5, 70]

        mic_on = (self._mode == "mic")
        bt_on = not mic_on

        d.rectangle(left, outline=neon_d, fill=(neon_d if mic_on else BG))
        d.rectangle(right, outline=neon_d, fill=(neon_d if bt_on else BG))

        d.text((left[0] + 10, left[1] + 9), "MIC", font=self.font, fill=(BG if mic_on else neon))
        d.text((right[0] + 10, right[1] + 9), "BT", font=self.font, fill=(BG if bt_on else neon))

        # effect + status
        d.text((8, 80), f"EFFECT: {self._effect}", font=self.font, fill=neon)
        d.text((8, 98), self._status, font=self.font, fill=neon_d)

        # big level bar
        d.rectangle([8, 120, self.W - 9, 142], outline=neon_d)
        fillw = int((self.W - 18) * self._level)
        if fillw > 0:
            d.rectangle([9, 121, 9 + fillw, 141], fill=neon)

        # mode info
        if mic_on:
            d.text((8, 152), "INPUT: MIC", font=self.font, fill=neon_d)
        else:
            d.text((8, 152), f"BT: {'ON' if self._bt_connected else 'OFF'}", font=self.font, fill=neon_d)
            if getattr(self, "_bt_name", ""):
                d.text((8, 170), self._bt_name, font=self.font, fill=neon)

        self.lcd.display(img)
