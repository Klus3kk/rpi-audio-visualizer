# firmware/ui/lcd_ui.py
import time
from PIL import Image, ImageDraw, ImageFont
from firmware.ui.lcd_st7789 import LcdSt7789

NEON = (0, 170, 255)
NEON2 = (0, 90, 140)
FG = (210, 240, 255)
BG = (0, 0, 0)

class LCDUI:
    """
    UI poziome 320x240:
    - tylko MIC / BT
    - czarne tło
    - prostokątne “nokia” elementy
    - odświeżanie ograniczone (żeby nie lagowało wizualizacji)
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

        self.dev = LcdSt7789(
            width=int(self.cfg.get("width", 240)),
            height=int(self.cfg.get("height", 320)),
            spi_bus=int(self.cfg.get("spi_bus", 0)),
            spi_dev=int(self.cfg.get("spi_dev", 0)),
            spi_hz=int(self.cfg.get("spi_hz", 40_000_000)),
            dc=int(self.cfg.get("dc", 25)),
            rst=int(self.cfg.get("rst", 24)),
            rotate=int(self.cfg.get("rotate", 90)),
            invert=bool(self.cfg.get("invert", True)),
            madctl_base=int(self.cfg.get("madctl_base", 0x00)),
        )

        self.W, self.H = self.dev.W, self.dev.H

        # font: default jest OK; “dziwne obroty” były od złej rotacji panelu
        self.font = ImageFont.load_default()

        self.mode = "MIC"
        self.effect = "bars"
        self.rms = 0.0
        self.energy = 0.0
        self.last_draw = 0.0
        self.min_period = float(self.cfg.get("ui_fps", 10.0))
        self._dirty = True

    def set_mode(self, mode: str):
        mode = "BT" if str(mode).upper().startswith("B") else "MIC"
        if mode != self.mode:
            self.mode = mode
            self._dirty = True

    def set_status(self, *, effect=None, rms=None, energy=None):
        if effect is not None and effect != self.effect:
            self.effect = str(effect)
            self._dirty = True
        if rms is not None:
            self.rms = float(rms)
        if energy is not None:
            self.energy = float(energy)

    def tick(self):
        now = time.monotonic()
        if not self._dirty and (now - self.last_draw) < (1.0 / max(1e-6, self.min_period)):
            return
        self.last_draw = now
        self._dirty = False
        self._render()

    def _render(self):
        img = Image.new("RGB", (self.W, self.H), BG)
        d = ImageDraw.Draw(img)

        # header tabs
        pad = 12
        tab_h = 44
        tab_w = (self.W - 3 * pad) // 2

        def tab(x, label, active):
            y = pad
            x0, y0 = x, y
            x1, y1 = x + tab_w, y + tab_h
            if active:
                d.rectangle([x0, y0, x1, y1], outline=NEON, width=3, fill=(0, 0, 0))
                d.text((x0 + 14, y0 + 14), label, font=self.font, fill=FG)
            else:
                d.rectangle([x0, y0, x1, y1], outline=NEON2, width=2, fill=(0, 0, 0))
                d.text((x0 + 14, y0 + 14), label, font=self.font, fill=NEON2)

        tab(pad, "MIC", self.mode == "MIC")
        tab(2 * pad + tab_w, "BT", self.mode == "BT")

        # main panel
        y0 = pad + tab_h + pad
        d.rectangle([pad, y0, self.W - pad, self.H - pad], outline=NEON2, width=2)

        # effect name
        d.text((pad + 14, y0 + 14), f"EFFECT: {self.effect}", font=self.font, fill=FG)

        # meters (nokia-like bars)
        # RMS bar
        rms = min(1.0, max(0.0, self.rms * 10.0))  # prosty scaling
        energy = min(1.0, max(0.0, self.energy))

        def meter(y, label, v):
            d.text((pad + 14, y), label, font=self.font, fill=NEON)
            x0 = pad + 14
            y0m = y + 18
            w = self.W - 2 * pad - 28
            h = 14
            d.rectangle([x0, y0m, x0 + w, y0m + h], outline=NEON2, width=2)
            fill_w = int(w * v)
            if fill_w > 0:
                d.rectangle([x0 + 2, y0m + 2, x0 + 2 + fill_w, y0m + h - 2], fill=NEON)

        meter(y0 + 54, "RMS", rms)
        meter(y0 + 92, "ENERGY", energy)

        # footer hint
        d.text((pad + 14, self.H - pad - 20), "Mode: MIC/BT", font=self.font, fill=NEON2)

        self.dev.display(img)