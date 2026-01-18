# firmware/ui/lcd_ui.py
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont

from firmware.ui.lcd_st7789 import LcdSt7789

@dataclass
class UIState:
    mode: str = "MIC"          # "MIC" albo "BT"
    effect: str = "bars"
    intensity: float = 0.75
    brightness: float = 0.25
    bt_connected: bool = False
    title: str = ""
    artist: str = ""

class LCDUI:
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.dev = LcdSt7789(
            width=int(self.cfg.get("width_panel", 240)),
            height=int(self.cfg.get("height_panel", 320)),
            spi_bus=int(self.cfg.get("spi_bus", 0)),
            spi_dev=int(self.cfg.get("spi_dev", 0)),
            spi_hz=int(self.cfg.get("spi_hz", 24_000_000)),
            dc=int(self.cfg.get("dc", 25)),
            rst=int(self.cfg.get("rst", 24)),
            bl=self.cfg.get("bl", None),
            cs_gpio=self.cfg.get("cs_gpio", None),
            rotate=int(self.cfg.get("rotate", 90)),
            invert=bool(self.cfg.get("invert", True)),
            madctl_base=int(self.cfg.get("madctl_base", 0x00)),
        )
        self.W, self.H = self.dev.W, self.dev.H
        self.font = ImageFont.load_default()

        # theme
        self.bg = (0, 0, 0)
        self.neon = (0, 170, 255)
        self.text = (210, 240, 255)
        self.dim = (60, 90, 110)

    def close(self):
        self.dev.close()

    def _clip(self, s: str, n: int) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[: max(0, n - 1)] + "…"

    def render(self, state: UIState, feats: dict):
        img = Image.new("RGB", (self.W, self.H), self.bg)
        d = ImageDraw.Draw(img)

        # top tabs
        d.rectangle([0, 0, self.W-1, 28], outline=self.neon, width=2)
        # MIC tab
        mic_on = (state.mode.upper() == "MIC")
        bt_on  = (state.mode.upper() == "BT")
        d.rectangle([2, 2, 78, 26], fill=(0, 40, 60) if mic_on else self.bg, outline=self.neon, width=1)
        d.rectangle([80, 2, 156, 26], fill=(0, 40, 60) if bt_on else self.bg, outline=self.neon, width=1)
        d.text((22, 9), "MIC", fill=self.text if mic_on else self.dim, font=self.font)
        d.text((107, 9), "BT",  fill=self.text if bt_on else self.dim, font=self.font)

        # main box
        y0 = 34
        d.rectangle([0, y0, self.W-1, self.H-1], outline=self.neon, width=2)

        # left info (Nokia vibe)
        d.text((10, y0+10), f"EFFECT: {self._clip(state.effect, 14)}", fill=self.text, font=self.font)
        d.text((10, y0+28), f"INT: {state.intensity:.2f}", fill=self.text, font=self.font)
        d.text((10, y0+44), f"BRI: {state.brightness:.2f}", fill=self.text, font=self.font)

        rms = float(feats.get("rms", 0.0))
        bass = float(feats.get("bass", 0.0))
        mid = float(feats.get("mid", 0.0))
        tre = float(feats.get("treble", 0.0))

        d.text((10, y0+70), f"RMS: {rms:.4f}", fill=self.text, font=self.font)
        d.text((10, y0+88), f"B:{bass:.2f} M:{mid:.2f} T:{tre:.2f}", fill=self.text, font=self.font)

        # right: simple neon meters (nie robią flasha)
        mx = self.W - 120
        d.text((mx, y0+10), "LEVEL", fill=self.neon, font=self.font)

        def bar(x, y, w, h, v):
            v = 0.0 if v < 0 else (1.0 if v > 1 else v)
            d.rectangle([x, y, x+w, y+h], outline=self.neon, width=1)
            fw = int(w * v)
            if fw > 0:
                d.rectangle([x+1, y+1, x+fw, y+h-1], fill=(0, 110, 170))

        # RMS bar (skalowanie “czytelne”)
        bar(mx, y0+28, 100, 10, min(1.0, rms * 18.0))
        bar(mx, y0+46, 100, 10, min(1.0, bass))
        bar(mx, y0+64, 100, 10, min(1.0, mid))
        bar(mx, y0+82, 100, 10, min(1.0, tre))

        d.text((mx, y0+104), "NOW", fill=self.neon, font=self.font)
        if bt_on:
            conn = "ON" if state.bt_connected else "OFF"
            d.text((mx, y0+122), f"BT: {conn}", fill=self.text, font=self.font)
        else:
            d.text((mx, y0+122), "SRC: MIC", fill=self.text, font=self.font)

        line = self._clip(f"{state.artist} - {state.title}".strip(" -"), 18)
        d.text((mx, y0+140), line, fill=self.text, font=self.font)

        self.dev.display(img)
