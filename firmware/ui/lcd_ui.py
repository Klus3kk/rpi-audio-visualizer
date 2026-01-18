# firmware/ui/lcd_ui.py
import time
import spidev
import lgpio
from PIL import Image, ImageDraw, ImageFont, ImageOps


class LCDUI:
    """
    Minimalny Nokia-like UI na ST7789 (SPI):
    - tylko MIC / BT
    - czarne tło + neon-cyan
    - spidev + lgpio
    - wspiera MIRROR (lustrzane odbicie) i panel inversion (INVON/INVOFF)
    """

    def __init__(
        self,
        *,
        spi_bus=0,
        spi_dev=0,
        spi_hz=24_000_000,
        dc=25,
        rst=24,
        cs_gpio=5,            # None jeśli używasz sprzętowego CE0/CE1
        rotate=90,            # 90 lub 270 (jak Ci pasuje)
        mirror=False,         # <-- TO jest "invert na drugą stronę" (lustrzane odbicie)
        panel_invert=False,   # <-- jeśli tło wychodzi białe: ustaw False (INVOFF)
        w_panel=240,
        h_panel=320,
        font_path="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        font_size=16,
        font_size_big=22,
        dim=0.85,
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

        # rysujemy logicznie w LANDSCAPE 320x240 i potem robimy rotate/mirror -> 240x320
        self.W = 320
        self.H = 240

        self.dim = float(dim)

        # ---- state (to będziesz ustawiać z runnera) ----
        self.mode = "mic"            # "mic" / "bt"
        self.effect = "bars"
        self.intensity = 0.75
        self.color_mode = "auto"

        self.rms = 0.0
        self.bass = 0.0
        self.mid = 0.0
        self.treble = 0.0

        self.bt_connected = False
        self.bt_name = ""
        self.bt_addr = ""

        self.artist = ""
        self.title = ""

        self.status = ""             # krótka linia statusu

        # fonts
        try:
            self.font = ImageFont.truetype(font_path, font_size)
            self.font_big = ImageFont.truetype(font_path, font_size_big)
            self.font_small = ImageFont.truetype(font_path, 13)
        except Exception:
            self.font = ImageFont.load_default()
            self.font_big = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

        # GPIO
        self.gh = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self.gh, self.DC, 0)
        lgpio.gpio_claim_output(self.gh, self.RST, 1)
        if self.CS is not None:
            lgpio.gpio_claim_output(self.gh, self.CS, 1)

        # SPI
        self.spi = spidev.SpiDev()
        self.spi.open(self.spi_bus, self.spi_dev)
        self.spi.max_speed_hz = self.spi_hz
        self.spi.mode = 0

        self._init_st7789()
        self._fill_black()

    # ---------------- public setters ----------------
    def set_mode(self, mode: str):
        self.mode = "bt" if str(mode).lower() == "bt" else "mic"

    def set_effect(self, effect: str):
        self.effect = (effect or "")[:20] or "bars"

    def set_visual_params(self, *, intensity=None, color_mode=None):
        if intensity is not None:
            x = float(intensity)
            if x < 0.0: x = 0.0
            if x > 1.0: x = 1.0
            self.intensity = x
        if color_mode is not None:
            self.color_mode = str(color_mode)[:12]

    def set_mic_feats(self, *, rms=0.0, bass=0.0, mid=0.0, treble=0.0):
        self.rms = float(rms)
        self.bass = float(bass)
        self.mid = float(mid)
        self.treble = float(treble)

    def set_bt(self, *, connected: bool, device_name: str = "", device_addr: str = ""):
        self.bt_connected = bool(connected)
        self.bt_name = (device_name or "")[:22]
        self.bt_addr = (device_addr or "")[:24]

    def set_track(self, *, artist: str = "", title: str = ""):
        self.artist = (artist or "")[:24]
        self.title = (title or "")[:24]

    def set_status(self, text: str):
        self.status = (text or "")[:28]

    def close(self):
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            lgpio.gpiochip_close(self.gh)
        except Exception:
            pass

    # ---------------- low-level HW ----------------
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
        self._w(self.RST, 1); time.sleep(0.02)
        self._w(self.RST, 0); time.sleep(0.05)
        self._w(self.RST, 1); time.sleep(0.12)

    def _init_st7789(self):
        self._reset()
        self._cmd(0x01); time.sleep(0.12)  # SWRESET
        self._cmd(0x11); time.sleep(0.12)  # SLPOUT
        self._cmd(0x3A); self._data([0x55])  # 16-bit
        self._cmd(0x36); self._data([0x00])  # MADCTL zostaw
        # WAŻNE: panel inversion (kolory). Jak tło wychodzi białe -> INVOFF (0x20)
        self._cmd(0x21 if self.panel_invert else 0x20)
        time.sleep(0.01)
        self._cmd(0x29); time.sleep(0.12)  # DISPON

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A); self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(0x2B); self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
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
            self.spi.writebytes(buf[i:i + chunk])
        self._cs_high()

    def _fill_black(self):
        img = Image.new("RGB", (self.WP, self.HP), (0, 0, 0))
        self._display_240x320(img)

    # ---------------- drawing ----------------
    @staticmethod
    def _clamp8(v: int) -> int:
        return 0 if v < 0 else (255 if v > 255 else v)

    def _mul(self, rgb, k: float):
        return (
            self._clamp8(int(rgb[0] * k)),
            self._clamp8(int(rgb[1] * k)),
            self._clamp8(int(rgb[2] * k)),
        )

    def _cut(self, s: str, n: int) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[: n - 1] + "…"

    def render(self):
        # neon palette (czarno-niebieskie)
        BG   = (0, 0, 0)
        ACC  = self._mul((30, 140, 255), self.dim)   # bardziej niebieski neon
        ACC2 = self._mul((10, 60, 120), self.dim)    # ciemniejszy niebieski
        TXT  = self._mul((220, 235, 255), self.dim)
        SUB  = self._mul((100, 130, 155), self.dim)
        GRID = self._mul((0, 45, 70), self.dim)

        img = Image.new("RGB", (self.W, self.H), BG)
        d = ImageDraw.Draw(img)

        # header (kanciaste, "Nokia")
        d.rectangle((0, 0, self.W - 1, 40), fill=BG, outline=GRID, width=2)
        d.text((10, 9), "VISUALIZER", fill=TXT, font=self.font)

        # status (jedna linia)
        if self.status:
            d.text((140, 11), self._cut(self.status, 18), fill=SUB, font=self.font_small)

        # mode badge
        badge = "MIC" if self.mode == "mic" else "BT"
        d.rectangle((self.W - 64, 8, self.W - 10, 32), fill=BG, outline=ACC, width=2)
        d.text((self.W - 52, 12), badge, fill=ACC, font=self.font)

        # main frame
        d.rectangle((10, 52, self.W - 10, self.H - 10), fill=BG, outline=GRID, width=2)

        # effect line
        d.text((18, 60), "EFFECT", fill=SUB, font=self.font_small)
        d.text((18, 78), self._cut(self.effect.upper(), 14), fill=TXT, font=self.font_big)

        # intensity + color_mode
        d.text((18, 110), f"INT {self.intensity:.2f}   CLR {self.color_mode}", fill=SUB, font=self.font_small)
        self._draw_bar(d, 18, 128, 150, 12, self.intensity, ACC, GRID)

        # right panel content depends on mode
        if self.mode == "mic":
            d.text((190, 60), "MIC INPUT", fill=ACC, font=self.font)
            d.text((190, 86), f"RMS {self.rms:.4f}", fill=TXT, font=self.font_small)
            d.text((190, 106), f"B {self.bass:.2f}", fill=SUB, font=self.font_small)
            d.text((190, 124), f"M {self.mid:.2f}", fill=SUB, font=self.font_small)
            d.text((190, 142), f"T {self.treble:.2f}", fill=SUB, font=self.font_small)
        else:
            d.text((190, 60), "BLUETOOTH", fill=ACC, font=self.font)
            st = "CONNECTED" if self.bt_connected else "IDLE"
            d.text((190, 86), st, fill=(ACC if self.bt_connected else SUB), font=self.font_small)

            if self.bt_name:
                d.text((190, 106), self._cut(self.bt_name, 16), fill=TXT, font=self.font_small)
            if self.bt_addr:
                d.text((190, 124), self._cut(self.bt_addr, 18), fill=SUB, font=self.font_small)

            # now playing (artist + title)
            line = ""
            if self.artist and self.title:
                line = f"{self.artist} - {self.title}"
            else:
                line = self.title or self.artist

            d.text((18, 158), "NOW PLAYING", fill=SUB, font=self.font_small)
            d.rectangle((18, 176, self.W - 18, 228), fill=BG, outline=ACC2, width=2)
            d.text((26, 188), self._cut(line, 28), fill=TXT, font=self.font)

        # --- transform to panel: mirror + rotate ---
        out = img
        if self.mirror:
            out = ImageOps.mirror(out)  # <-- lustrzane odbicie (to czego chcesz)
        out = out.rotate(self.rotate, expand=True)  # -> 240x320 (zależnie od rotate)
        if out.size != (self.WP, self.HP):
            out = out.resize((self.WP, self.HP))

        self._display_240x320(out)

    def _draw_bar(self, d, x, y, w, h, v, fill, outline):
        if v < 0.0: v = 0.0
        if v > 1.0: v = 1.0
        d.rectangle((x, y, x + w, y + h), fill=(0, 0, 0), outline=outline, width=2)
        fw = int((w - 4) * v)
        if fw > 0:
            d.rectangle((x + 2, y + 2, x + 2 + fw, y + h - 2), fill=fill)
