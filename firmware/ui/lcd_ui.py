import time
import spidev
import lgpio
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from typing import Optional


class LCDUI:
    def __init__(
        self,
        *,
        spi_bus=0,
        spi_dev=0,
        spi_hz=24_000_000,
        dc=25,
        rst=24,
        cs_gpio=5,
        rotate=270,
        mirror=True,
        panel_invert=False,
        w_panel=240,
        h_panel=320,
        font_path="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        font_size=13,
        font_size_big=18,
        accent=(30, 140, 255),
        bg=(0, 0, 0),
        dim=0.90,
    ):
        self.spi_bus = int(spi_bus)
        self.spi_dev = int(spi_dev)
        self.spi_hz = int(spi_hz)

        self.DC = int(dc)
        self.RST = int(rst)
        self.CS = None if cs_gpio is None else int(cs_gpio)

        self.rotate = int(rotate) % 360
        self.mirror = bool(mirror)
        self.panel_invert = bool(panel_invert)

        self.WP = int(w_panel)
        self.HP = int(h_panel)

        self.W = 320
        self.H = 240

        self.bg = tuple(bg)
        self.accent = tuple(accent)
        self.dim = float(dim)

        self.mode = "mic"
        self.effect = "bars"
        self.intensity = 0.75
        self.color_mode = "auto"
        self.gain = 1.0
        self.smoothing = 0.65

        self.rms = 0.0
        self.bass = 0.0
        self.mid = 0.0
        self.treble = 0.0

        self.status = ""
        self.bt_name = ""
        self.bt_addr = ""
        self.bt_connected = False
        self.artist = ""
        self.title = ""
        self.album = ""

        self._cover_cache: Optional[Image.Image] = None

        try:
            self.font = ImageFont.truetype(font_path, font_size)
            self.font_big = ImageFont.truetype(font_path, font_size_big)
            self.font_small = ImageFont.truetype(font_path, max(10, font_size - 2))
        except Exception:
            self.font = ImageFont.load_default()
            self.font_big = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

        self.gh = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self.gh, self.DC, 0)
        lgpio.gpio_claim_output(self.gh, self.RST, 1)
        if self.CS is not None:
            lgpio.gpio_claim_output(self.gh, self.CS, 1)

        self.spi = spidev.SpiDev()
        self.spi.open(self.spi_bus, self.spi_dev)
        self.spi.max_speed_hz = self.spi_hz
        self.spi.mode = 0

        self._init_st7789()
        self._fill_black()

    def set_mode(self, mode: str):
        self.mode = "bt" if str(mode).lower() == "bt" else "mic"

    def set_effect(self, effect: str):
        self.effect = (effect or "")[:12]

    def set_visual_params(self, *, intensity: float, color_mode: str = "auto"):
        try:
            x = float(intensity)
        except Exception:
            x = self.intensity
        if x < 0.0:
            x = 0.0
        if x > 1.0:
            x = 1.0
        self.intensity = x

        cm = str(color_mode or "auto").lower()
        if cm not in ("auto", "rainbow", "mono"):
            cm = "auto"
        self.color_mode = cm

    def set_audio_params(self, *, gain: float, smoothing: float):
        try:
            g = float(gain)
        except Exception:
            g = self.gain
        if not np.isfinite(g):
            g = self.gain
        self.gain = max(0.1, min(6.0, g))

        try:
            s = float(smoothing)
        except Exception:
            s = self.smoothing
        if not np.isfinite(s):
            s = self.smoothing
        self.smoothing = max(0.0, min(0.95, s))

    def set_mic_feats(self, *, rms: float, bass: float, mid: float, treble: float):
        self.rms = float(rms)
        self.bass = float(bass)
        self.mid = float(mid)
        self.treble = float(treble)

    def set_status(self, text: str):
        self.status = (text or "")[:34]

    def set_bt(self, *, connected: bool, device_name: str = "", device_addr: str = ""):
        self.bt_connected = bool(connected)
        self.bt_name = (device_name or "")[:22]
        self.bt_addr = (device_addr or "")[:22]

    def set_track(self, *, artist: str = "", title: str = "", album: str = ""):
        self.artist = (artist or "")[:32]
        self.title = (title or "")[:32]
        self.album = (album or "")[:32]

    def close(self):
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            lgpio.gpiochip_close(self.gh)
        except Exception:
            pass

    def _w(self, pin, val):
        lgpio.gpio_write(self.gh, pin, 1 if val else 0)

    def _cs_low(self):
        if self.CS is not None:
            self._w(self.CS, 0)

    def _cs_high(self):
        if self.CS is not None:
            self._w(self.CS, 1)

    def _cmd(self, c: int):
        self._w(self.DC, 0)
        self._cs_low()
        self.spi.writebytes([c & 0xFF])
        self._cs_high()

    def _data(self, buf):
        if not buf:
            return
        self._w(self.DC, 1)
        self._cs_low()
        self.spi.writebytes(list(buf))
        self._cs_high()

    def _reset(self):
        self._w(self.RST, 1)
        time.sleep(0.02)
        self._w(self.RST, 0)
        time.sleep(0.05)
        self._w(self.RST, 1)
        time.sleep(0.12)

    def _init_st7789(self):
        self._reset()
        self._cmd(0x01)
        time.sleep(0.12)
        self._cmd(0x11)
        time.sleep(0.12)
        self._cmd(0x3A)
        self._data([0x55])
        self._cmd(0x36)
        self._data([0x00])
        if self.panel_invert:
            self._cmd(0x21)
        else:
            self._cmd(0x20)
        self._cmd(0x29)
        time.sleep(0.12)

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(0x2B)
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._cmd(0x2C)

    def _img_to_rgb565(self, img240x320: Image.Image) -> bytearray:
        img = img240x320.convert("RGB")
        px = img.load()
        out = bytearray(self.WP * self.HP * 2)
        i = 0
        for y in range(self.HP):
            for x in range(self.WP):
                r, g, b = px[x, y]
                v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                out[i] = (v >> 8) & 0xFF
                out[i + 1] = v & 0xFF
                i += 2
        return out

    def _display_240x320(self, img240x320: Image.Image):
        self._set_window(0, 0, self.WP - 1, self.HP - 1)
        buf = self._img_to_rgb565(img240x320)
        self._w(self.DC, 1)
        self._cs_low()
        chunk = 4096
        for i in range(0, len(buf), chunk):
            self.spi.writebytes(buf[i : i + chunk])
        self._cs_high()

    def _fill_black(self):
        img = Image.new("RGB", (self.WP, self.HP), (0, 0, 0))
        self._display_240x320(img)

    @staticmethod
    def _clamp8(x: int) -> int:
        return 0 if x < 0 else (255 if x > 255 else x)

    def _mul(self, c, k):
        return (
            self._clamp8(int(c[0] * k)),
            self._clamp8(int(c[1] * k)),
            self._clamp8(int(c[2] * k)),
        )

    @staticmethod
    def _ell(s: str, n: int) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else (s[: max(0, n - 1)] + "…")

    def render(self):
        ACC = self._mul(self.accent, self.dim)
        TXT = self._mul((230, 240, 255), self.dim)
        SUB = self._mul((110, 130, 150), self.dim)
        GRID = self._mul((0, 50, 90), self.dim)

        img = Image.new("RGB", (self.W, self.H), self.bg)
        d = ImageDraw.Draw(img)

        d.rectangle((0, 0, self.W - 1, 34), fill=(0, 0, 0), outline=GRID, width=2)
        d.text((10, 7), "VISUALIZER", fill=TXT, font=self.font)
        d.text((170, 7), self._ell(f"FX:{self.effect}", 12), fill=SUB, font=self.font)

        tab_y0, tab_y1 = 40, 72

        def tab(x0, label, active):
            x1 = x0 + 90
            d.rectangle(
                (x0, tab_y0, x1, tab_y1),
                fill=(0, 0, 0),
                outline=(ACC if active else GRID),
                width=(3 if active else 2),
            )
            d.text((x0 + 18, tab_y0 + 9), label, fill=(ACC if active else SUB), font=self.font)

        tab(10, "MIC", self.mode == "mic")
        tab(110, "BT", self.mode == "bt")

        d.rectangle((10, 78, self.W - 10, self.H - 10), fill=(0, 0, 0), outline=GRID, width=2)

        if self.mode == "mic":
            d.text((18, 86), "AUDIO", fill=ACC, font=self.font)
            d.text((18, 106), f"RMS {self.rms:.3f}", fill=TXT, font=self.font_small)
            d.text((18, 124), f"B  {self.bass:.2f}", fill=SUB, font=self.font_small)
            d.text((18, 140), f"M  {self.mid:.2f}", fill=SUB, font=self.font_small)
            d.text((18, 156), f"T  {self.treble:.2f}", fill=SUB, font=self.font_small)

            rx = 150
            d.text((rx, 86), "MODE", fill=ACC, font=self.font)
            d.text((rx, 106), "MIC INPUT", fill=TXT, font=self.font_small)

        else:
            if self.bt_connected:
                d.text((18, 110), "NOW PLAYING", fill=ACC, font=self.font_small)
                artist_txt = self._ell(self.artist or "Unknown Artist", 24)
                d.text((18, 130), artist_txt, fill=TXT, font=self.font_big)

                title_txt = self._ell(self.title or "Unknown Title", 28)
                d.text((18, 155), title_txt, fill=TXT, font=self.font)

                if self.album:
                    album_txt = self._ell(self.album, 28)
                    d.text((18, 175), album_txt, fill=SUB, font=self.font_small)

                d.text((18, 200), "DEVICE", fill=ACC, font=self.font_small)
                d.text((18, 216), self._ell(self.bt_name, 24), fill=SUB, font=self.font_small)
            else:
                d.text((18, 110), "NOT CONNECTED", fill=SUB, font=self.font)

        d.rectangle((10, self.H - 38, self.W - 10, self.H - 10), fill=(0, 0, 0), outline=GRID, width=2)
        d.text((18, self.H - 32), f"INT {self.intensity:.2f}", fill=SUB, font=self.font_small)
        d.text((120, self.H - 32), f"GAIN {self.gain:.2f}", fill=SUB, font=self.font_small)
        d.text((230, self.H - 32), f"SM {self.smoothing:.2f}", fill=SUB, font=self.font_small)

        out = img.rotate(self.rotate, expand=True)
        if self.mirror:
            out = ImageOps.mirror(out)

        if out.size != (self.WP, self.HP):
            out = out.resize((self.WP, self.HP))

        self._display_240x320(out)
