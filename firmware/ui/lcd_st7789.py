import time
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import spi, gpio
from luma.lcd.device import st7789

class LcdSt7789:
    def __init__(self, width=240, height=320, spi_port=0, spi_device=0, dc=25, rst=24, cs=5, rotate=0):
        serial = spi(port=spi_port, device=spi_device, gpio=gpio(dc=dc, rst=rst))
        self.dev = st7789(serial, width=width, height=height, rotate=rotate, cs=cs)
        self.font = ImageFont.load_default()
        self.w = width
        self.h = height

    def render_status(self, state, feats, nowp=None):
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (self.w, self.h), "black")
        d = ImageDraw.Draw(img)

        nowp = nowp or {"source": state.mode, "connected": False, "title": "", "artist": "", "album": ""}
        
        # progress (dla local)
        if nowp.get("source") == "local" and nowp.get("connected"):
            tpos = float(nowp.get("time_pos") or 0.0)
            dur = float(nowp.get("duration") or 0.0)
            pct = 0.0 if dur <= 0 else max(0.0, min(1.0, tpos / dur))

            bar_x, bar_y, bar_w, bar_h = 10, 220, self.w - 20, 10
            d.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline="white")
            d.rectangle([bar_x, bar_y, bar_x + int(bar_w * pct), bar_y + bar_h], fill="white")

            def fmt(sec):
                sec = int(sec)
                return f"{sec//60}:{sec%60:02d}"

            d.text((10, 240), f"{fmt(tpos)} / {fmt(dur)}", font=self.font, fill="white")

        d.text((10, 10), f"MODE: {state.mode}", font=self.font, fill="white")
        d.text((10, 30), f"EFFECT: {state.effect}", font=self.font, fill="white")
        d.text((10, 50), f"BRI: {state.brightness:.2f}  INT: {state.intensity:.2f}", font=self.font, fill="white")
        d.text((10, 70), f"GAIN: {state.gain:.2f}  SM: {state.smoothing:.2f}", font=self.font, fill="white")

        # audio features
        d.text((10, 100), f"RMS: {feats['rms']:.4f}", font=self.font, fill="white")
        d.text((10, 120), f"B:{feats['bass']:.2f} M:{feats['mid']:.2f} T:{feats['treble']:.2f}", font=self.font, fill="white")

        # now playing / connection
        conn = "ON" if nowp.get("connected") else "OFF"
        d.text((10, 150), f"SRC: {nowp.get('source','')}  BT: {conn}", font=self.font, fill="white")

        artist = (nowp.get("artist") or "").strip()
        title = (nowp.get("title") or "").strip()
        line = f"{artist} — {title}" if artist and title else (title or artist or "")

        # proste ucinanie
        if len(line) > 28:
            line = line[:27] + "…"

        d.text((10, 170), "NOW:", font=self.font, fill="white")
        d.text((10, 190), line, font=self.font, fill="white")

        self.dev.display(img)
