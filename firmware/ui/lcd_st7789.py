# firmware/ui/lcd_st7789.py
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import spi, gpio
from luma.lcd.device import st7789


NEON = (0, 200, 255)
NEON2 = (40, 120, 255)
BG = (0, 0, 0)
DIM = (0, 50, 70)


class LcdSt7789:
    """
    Luma ST7789 wrapper.
    KLUCZ: rysujemy zawsze w rozmiarze self.dev.size, a nie "width/height z configu".
    To usuwa cyrki z obróconym fontem po rotate.
    """

    def __init__(
        self,
        width=240,
        height=320,
        spi_port=0,
        spi_device=0,
        dc=25,
        rst=24,
        cs=5,
        rotate=1,         # 0/1/2/3 => 0/90/180/270
        spi_hz=32_000_000
    ):
        serial = spi(
            port=int(spi_port),
            device=int(spi_device),
            gpio=gpio(dc=int(dc), rst=int(rst)),
            bus_speed_hz=int(spi_hz),
        )

        # UWAGA: cs w luma zwykle jest pinem CE0/CE1 albo "GPIO CS" zależnie od setupu.
        self.dev = st7789(serial, width=int(width), height=int(height), rotate=int(rotate), cs=cs)

        # NAJWAŻNIEJSZE: realny rozmiar po rotate
        self.w, self.h = self.dev.size

        self.font = ImageFont.load_default()

    def render_ui(self, *, mode: str, effect: str, feats: dict, bt_connected: bool, nowp: dict | None = None):
        """
        mode: "MIC" albo "BT"
        effect: nazwa efektu
        feats: dict z FeatureExtractor: rms, bass, mid, treble
        nowp: opcjonalnie: {"title": "...", "artist":"...", "connected": bool}
        """
        mode = (mode or "MIC").upper()
        effect = str(effect or "")
        nowp = nowp or {}

        img = Image.new("RGB", (self.w, self.h), BG)
        d = ImageDraw.Draw(img)

        # Header
        d.rectangle([6, 6, self.w - 7, 42], outline=NEON2)
        d.text((14, 14), "AUDIO VIS", fill=NEON, font=self.font)

        # MIC / BT buttons (Nokia-ish, prostokąty)
        mic_on = (mode == "MIC")
        bt_on = (mode == "BT")

        left = [6, 52, (self.w // 2) - 4, 88]
        right = [(self.w // 2) + 3, 52, self.w - 7, 88]

        d.rectangle(left, outline=NEON2, fill=(NEON2 if mic_on else BG))
        d.rectangle(right, outline=NEON2, fill=(NEON2 if bt_on else BG))

        d.text((left[0] + 14, left[1] + 10), "MIC", fill=(BG if mic_on else NEON), font=self.font)
        d.text((right[0] + 14, right[1] + 10), "BT", fill=(BG if bt_on else NEON), font=self.font)

        # Status lines
        d.text((10, 102), f"EFFECT: {effect[:18]}", fill=NEON, font=self.font)
        d.text((10, 122), f"BT: {'ON' if bt_connected else 'OFF'}", fill=(NEON if bt_connected else DIM), font=self.font)

        # Audio meters
        rms = float(feats.get("rms", 0.0))
        bass = float(feats.get("bass", 0.0))
        mid = float(feats.get("mid", 0.0))
        treb = float(feats.get("treble", 0.0))

        def bar(y, label, v):
            v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
            x0, x1 = 10, self.w - 10
            d.text((10, y - 14), label, fill=NEON2, font=self.font)
            d.rectangle([x0, y, x1, y + 12], outline=NEON2)
            fillw = int((x1 - x0 - 2) * v)
            if fillw > 0:
                d.rectangle([x0 + 1, y + 1, x0 + 1 + fillw, y + 11], fill=NEON)

        # RMS map (czułość UI tylko do paska, nie zmienia LED)
        rms_v = max(0.0, min(1.0, rms * 14.0))
        bar(156, "RMS", rms_v)
        bar(196, "BASS", bass)
        bar(236, "MID", mid)
        bar(276, "TREB", treb)

        # Now playing (opcjonalnie; utnij, bez bajerów)
        artist = (nowp.get("artist") or "").strip()
        title = (nowp.get("title") or "").strip()
        line = f"{artist} — {title}" if artist and title else (title or artist or "")
        if len(line) > 26:
            line = line[:25] + "…"
        d.text((10, self.h - 20), line, fill=DIM, font=self.font)

        self.dev.display(img)
