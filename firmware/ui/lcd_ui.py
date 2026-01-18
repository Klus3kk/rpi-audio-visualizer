# firmware/ui/lcd_ui.py
import time
from PIL import Image, ImageDraw, ImageFont

from firmware.ui.lcd_st7789 import LcdSt7789


class LCDUI:
    """
    Minimalne UI:
      - tylko MIC / BT
      - czarne tło
      - neonowy niebieski
      - “Nokia-ish”: proste prostokąty, bez rounded
      - odświeżaj rzadko (w pętli głównej throttling)
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.W = int(self.cfg.get("width_panel", 240))
        self.H = int(self.cfg.get("height_panel", 320))

        self.dev = LcdSt7789(
            width=self.W,
            height=self.H,
            spi_bus=int(self.cfg.get("spi_bus", 0)),
            spi_dev=int(self.cfg.get("spi_dev", 0)),
            spi_hz=int(self.cfg.get("spi_hz", 24_000_000)),
            dc=int(self.cfg.get("dc", 25)),
            rst=int(self.cfg.get("rst", 24)),
            cs=self.cfg.get("cs", 5),
            invert=bool(self.cfg.get("invert", True)),
            rotate=int(self.cfg.get("rotate", 90)),
            madctl_base=int(self.cfg.get("madctl_base", 0x00)),
        )

        # po rotate=90 logika ekranu jest 320x240
        self.w = self.dev.w
        self.h = self.dev.h

        self.font = ImageFont.load_default()
        self.mode = "MIC"  # MIC / BT
        self.effect = "bars"
        self.bt_status = "disconnected"

        self._t = 0.0

        # theme
        self.bg = (0, 0, 0)
        self.neon = (0, 180, 255)
        self.dim = (0, 70, 110)
        self.gray = (60, 60, 60)
        self.white = (220, 220, 220)

        # start screen
        self.draw({"rms": 0.0, "level": 0.0})

    def set_mode(self, mode: str):
        mode = (mode or "").upper()
        self.mode = "BT" if mode.startswith("B") else "MIC"

    def set_effect(self, name: str):
        self.effect = str(name or "bars")

    def set_bt_status(self, s: str):
        self.bt_status = str(s or "unknown")

    def _bar(self, d: ImageDraw.ImageDraw, x, y, w, h, v01):
        v01 = 0.0 if v01 < 0.0 else (1.0 if v01 > 1.0 else float(v01))
        d.rectangle([x, y, x + w, y + h], outline=self.dim, width=1)
        fillw = int(w * v01)
        if fillw > 0:
            d.rectangle([x + 1, y + 1, x + fillw, y + h - 1], fill=self.neon)

    def draw(self, state: dict):
        """
        state: {"rms": float, "level": 0..1 (opcjonalnie), "effect": str (opcjonalnie)}
        """
        rms = float(state.get("rms", 0.0))
        level = float(state.get("level", min(1.0, rms * 12.0)))
        effect = state.get("effect", None)
        if effect:
            self.effect = str(effect)

        img = Image.new("RGB", (self.w, self.h), self.bg)
        d = ImageDraw.Draw(img)

        # header
        d.rectangle([0, 0, self.w - 1, 34], outline=self.dim, width=1)
        d.text((10, 10), "VISUALIZER", fill=self.neon, font=self.font)

        # mode switch: MIC / BT
        # proste “kafelki”
        bx = self.w - 140
        by = 8
        bw = 60
        bh = 18

        def pill(x, label, active):
            d.rectangle([x, by, x + bw, by + bh], outline=self.neon if active else self.dim, width=1)
            d.text((x + 12, by + 4), label, fill=self.neon if active else self.dim, font=self.font)

        pill(bx, "MIC", self.mode == "MIC")
        pill(bx + 70, "BT", self.mode == "BT")

        # body boxes
        y0 = 44
        d.rectangle([10, y0, self.w - 11, y0 + 52], outline=self.dim, width=1)
        d.text((18, y0 + 10), f"EFFECT: {self.effect}", fill=self.white, font=self.font)

        # BT status (tylko gdy BT)
        if self.mode == "BT":
            d.text((18, y0 + 30), f"BT: {self.bt_status}", fill=self.white, font=self.font)
        else:
            d.text((18, y0 + 30), "INPUT: MIC", fill=self.white, font=self.font)

        # level bar
        y1 = y0 + 70
        d.text((10, y1), "LEVEL", fill=self.dim, font=self.font)
        self._bar(d, 10, y1 + 16, self.w - 21, 16, level)

        # footer “hint”
        d.rectangle([0, self.h - 28, self.w - 1, self.h - 1], outline=self.dim, width=1)
        d.text((10, self.h - 20), "BTN: hold to switch mode", fill=self.dim, font=self.font)

        self.dev.display(img)

    def close(self):
        self.dev.close()
