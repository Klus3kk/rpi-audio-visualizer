# firmware/ui/lcd_ui.py
from PIL import Image, ImageDraw
from firmware.ui.lcd_st7789 import LcdSt7789

NEON = (0, 200, 255)
NEON2 = (40, 120, 255)
BG = (0, 0, 0)
DIM = (0, 50, 70)

class LCDUI:
    def __init__(self, cfg: dict):
        cfg = cfg or {}
        self.dev = LcdSt7789(
            width=int(cfg.get("width", 240)),
            height=int(cfg.get("height", 320)),
            spi_bus=int(cfg.get("spi_bus", 0)),
            spi_dev=int(cfg.get("spi_dev", 0)),
            spi_hz=int(cfg.get("spi_hz", 40_000_000)),
            dc=int(cfg.get("dc", 25)),
            rst=int(cfg.get("rst", 24)),
            cs_gpio=(None if cfg.get("cs_gpio", None) in (None, "None") else int(cfg.get("cs_gpio"))),
            rotate=int(cfg.get("rotate", 90)),
            invert=bool(cfg.get("invert", True)),
            madctl_rgb=bool(cfg.get("madctl_rgb", True)),
        )

    def close(self):
        self.dev.close()

    def render(self, *, mode: str, effect: str, feats: dict, bt_connected: bool, nowp=None):
        mode = (mode or "MIC").upper()
        effect = (effect or "")[:18]
        nowp = nowp or {}

        img = Image.new("RGB", (self.dev.w, self.dev.h), BG)
        d = ImageDraw.Draw(img)

        # header
        d.rectangle([6, 6, self.dev.w - 7, 42], outline=NEON2)
        d.text((14, 14), "AUDIO VIS", fill=NEON)

        # mic/bt buttons
        mic_on = (mode == "MIC")
        bt_on = (mode == "BT")

        left = [6, 52, (self.dev.w // 2) - 4, 88]
        right = [(self.dev.w // 2) + 3, 52, self.dev.w - 7, 88]

        d.rectangle(left, outline=NEON2, fill=(NEON2 if mic_on else BG))
        d.rectangle(right, outline=NEON2, fill=(NEON2 if bt_on else BG))

        d.text((left[0] + 14, left[1] + 10), "MIC", fill=(BG if mic_on else NEON))
        d.text((right[0] + 14, right[1] + 10), "BT", fill=(BG if bt_on else NEON))

        # effect + bt status
        d.text((10, 102), f"EFFECT: {effect}", fill=NEON)
        d.text((10, 122), f"BT: {'ON' if bt_connected else 'OFF'}", fill=(NEON if bt_connected else DIM))

        # bars
        rms = float(feats.get("rms", 0.0))
        bass = float(feats.get("bass", 0.0))
        mid = float(feats.get("mid", 0.0))
        treb = float(feats.get("treble", 0.0))

        def bar(y, label, v):
            v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
            x0, x1 = 10, self.dev.w - 10
            d.text((10, y - 14), label, fill=NEON2)
            d.rectangle([x0, y, x1, y + 12], outline=NEON2)
            fillw = int((x1 - x0 - 2) * v)
            if fillw > 0:
                d.rectangle([x0 + 1, y + 1, x0 + 1 + fillw, y + 11], fill=NEON)

        bar(156, "RMS", max(0.0, min(1.0, rms * 14.0)))
        bar(196, "BASS", bass)
        bar(236, "MID", mid)
        bar(276, "TREB", treb)

        # now playing line (opcjonalnie)
        artist = (nowp.get("artist") or "").strip()
        title = (nowp.get("title") or "").strip()
        line = f"{artist} — {title}" if artist and title else (title or artist or "")
        if len(line) > 26:
            line = line[:25] + "…"
        d.text((10, self.dev.h - 20), line, fill=DIM)

        self.dev.display(img)
