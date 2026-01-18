# firmware/ui/lcd_ui.py
# Nokia-like UI: black bg, neon blue lines, ONLY 2 modes: MIC / BT.
# Correct rotation: uses transpose(), never rotate()/resize() (fixes weird font).

from PIL import Image, ImageDraw, ImageFont
import time


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


class LCDUI:
    """
    Usage:
      ui = LCDUI({
        "width_panel": 240, "height_panel": 320,
        "rotate": 270,          # 90 or 270 usually for landscape UI
        "spi_bus": 0, "spi_dev": 0, "spi_hz": 40_000_000,
        "dc": 25, "rst": 24, "cs": None,
        "invert": True,
      })
      ui.set_mode("mic"|"bt")
      ui.set_status(...)
      ui.render()
    """

    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})

        # Panel is 240x320 physically
        self.WP = int(self.cfg.get("width_panel", 240))
        self.HP = int(self.cfg.get("height_panel", 320))

        # We render UI in landscape by default: 320x240
        self.W = int(self.cfg.get("width_ui", 320))
        self.H = int(self.cfg.get("height_ui", 240))

        self.rotate = int(self.cfg.get("rotate", 270))  # final transpose to panel
        self.bg = (0, 0, 0)
        self.fg = (40, 170, 255)          # neon blue (main)
        self.fg2 = (20, 90, 160)          # dim blue (secondary)
        self.accent = (0, 255, 255)       # cyan highlight
        self.white = (220, 240, 255)      # pale white-ish

        self.mode = "mic"                 # "mic" or "bt"
        self.effect_name = "bars"
        self.intensity = 0.75
        self.color_mode = "auto"
        self.fps = 0.0
        self.rms = 0.0
        self.energy = 0.0
        self.msg = ""
        self._t0 = time.monotonic()

        self.font = self._load_font()

        from firmware.ui.lcd_st7789 import LcdSt7789
        self.dev = LcdSt7789(
            width=self.WP,
            height=self.HP,
            spi_bus=int(self.cfg.get("spi_bus", 0)),
            spi_dev=int(self.cfg.get("spi_dev", 0)),
            spi_hz=int(self.cfg.get("spi_hz", 40_000_000)),
            dc=int(self.cfg.get("dc", 25)),
            rst=int(self.cfg.get("rst", 24)),
            cs=self.cfg.get("cs", None),
            invert=bool(self.cfg.get("invert", True)),
            madctl=int(self.cfg.get("madctl", 0x00)),
        )

    def _load_font(self):
        # Prefer a monospace TTF if available; fallback to default bitmap.
        candidates = [
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]
        for p in candidates:
            try:
                return ImageFont.truetype(p, 16)
            except Exception:
                pass
        return ImageFont.load_default()

    # ---- state setters ----
    def set_mode(self, mode: str):
        self.mode = "bt" if str(mode).lower().startswith("b") else "mic"

    def set_effect(self, name: str):
        self.effect_name = str(name)

    def set_audio(self, *, rms: float, energy: float):
        self.rms = float(rms)
        self.energy = float(energy)

    def set_params(self, *, intensity=None, color_mode=None, fps=None):
        if intensity is not None:
            self.intensity = float(intensity)
        if color_mode is not None:
            self.color_mode = str(color_mode)
        if fps is not None:
            self.fps = float(fps)

    def set_status(self, msg: str):
        self.msg = str(msg)

    # ---- drawing ----
    def _draw_header(self, d: ImageDraw.ImageDraw):
        # top frame line
        d.rectangle([0, 0, self.W - 1, 26], outline=self.fg2, fill=self.bg)

        # tabs (MIC / BT)
        tab_w = (self.W - 6) // 2
        y0, y1 = 4, 22

        def tab(x0, label, active):
            x1 = x0 + tab_w
            col = self.accent if active else self.fg2
            d.rectangle([x0, y0, x1, y1], outline=col, fill=self.bg)
            d.text((x0 + 10, y0 + 3), label, font=self.font, fill=col)

        tab(2, "MIC", self.mode == "mic")
        tab(2 + tab_w + 2, "BT", self.mode == "bt")

    def _draw_body(self, d: ImageDraw.ImageDraw):
        # big body frame
        d.rectangle([2, 30, self.W - 3, self.H - 28], outline=self.fg2, fill=self.bg)

        # left info
        x0, y0 = 10, 38
        d.text((x0, y0), "EFFECT:", font=self.font, fill=self.fg2)
        d.text((x0 + 80, y0), self.effect_name.upper(), font=self.font, fill=self.fg)

        y0 += 22
        d.text((x0, y0), "COLOR:", font=self.font, fill=self.fg2)
        d.text((x0 + 80, y0), str(self.color_mode).upper(), font=self.font, fill=self.fg)

        y0 += 22
        d.text((x0, y0), "INT:", font=self.font, fill=self.fg2)
        d.text((x0 + 80, y0), f"{self.intensity:.2f}", font=self.font, fill=self.fg)

        y0 += 22
        d.text((x0, y0), "FPS:", font=self.font, fill=self.fg2)
        d.text((x0 + 80, y0), f"{self.fps:4.1f}", font=self.font, fill=self.fg)

        # right “meters”
        bx0 = self.W - 150
        by0 = 44
        bw = 130
        bh = 10

        def bar(y, label, v):
            v = _clamp(float(v), 0.0, 1.0)
            d.text((bx0, y - 2), label, font=self.font, fill=self.fg2)
            x1 = bx0 + bw
            d.rectangle([bx0 + 52, y, x1, y + bh], outline=self.fg2, fill=self.bg)
            fillw = int((bw - 2) * v)
            if fillw > 0:
                d.rectangle([bx0 + 53, y + 1, bx0 + 53 + fillw, y + bh - 1], outline=None, fill=self.fg)

        # map rms/energy into 0..1 visual scale
        rms_v = _clamp(self.rms * 8.0, 0.0, 1.0)
        eng_v = _clamp(self.energy * 1.6, 0.0, 1.0)

        bar(by0, "RMS", rms_v)
        bar(by0 + 22, "ENG", eng_v)

        # mode hint text
        y = self.H - 52
        if self.mode == "mic":
            d.text((10, y), "MIC MODE: live input", font=self.font, fill=self.white)
        else:
            d.text((10, y), "BT MODE: waiting device", font=self.font, fill=self.white)

    def _draw_footer(self, d: ImageDraw.ImageDraw):
        # bottom line
        d.rectangle([0, self.H - 24, self.W - 1, self.H - 1], outline=self.fg2, fill=self.bg)
        t = time.monotonic() - self._t0
        left = f"{t:6.1f}s"
        d.text((8, self.H - 20), left, font=self.font, fill=self.fg2)
        if self.msg:
            # cut message to fit
            d.text((90, self.H - 20), self.msg[:28], font=self.font, fill=self.fg)

    def render(self):
        # draw in UI-landscape resolution (W,H)
        img = Image.new("RGB", (self.W, self.H), self.bg)
        d = ImageDraw.Draw(img)

        self._draw_header(d)
        self._draw_body(d)
        self._draw_footer(d)

        # --- FIX: correct rotation without ruining font ---
        # NEVER use rotate(expand=True) here.
        if self.rotate == 90:
            out = img.transpose(Image.ROTATE_90)     # 320x240 -> 240x320
        elif self.rotate == 270:
            out = img.transpose(Image.ROTATE_270)
        elif self.rotate == 180:
            out = img.transpose(Image.ROTATE_180)
        else:
            out = img

        # If mismatch: DO NOT resize (resampling breaks font). Paste on black.
        if out.size != (self.WP, self.HP):
            canvas = Image.new("RGB", (self.WP, self.HP), self.bg)
            ox, oy = out.size
            px = (self.WP - ox) // 2
            py = (self.HP - oy) // 2
            canvas.paste(out, (px, py))
            out = canvas

        self.dev.display(out)

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass
