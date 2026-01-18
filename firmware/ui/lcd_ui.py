# firmware/ui/lcd_ui.py
import time
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont

import spidev
import lgpio


@dataclass
class NowPlaying:
    artist: str = ""
    title: str = ""


class LCDUI:
    """
    Minimalny Nokia-like UI na ST7789 (SPI):
    - tylko MIC / BT
    - czarne tło + neon blue
    - zero animacji
    - orientacja robiona MADCTL (nie PIL.rotate), żeby font nie był “odwrócony”
    """

    def __init__(
        self,
        *,
        spi_bus=0,
        spi_dev=0,
        spi_hz=24_000_000,
        dc=25,
        rst=24,
        cs_gpio=5,            # None jeśli używasz CE0/CE1
        w_panel=240,
        h_panel=320,
        rotate=90,            # 0/90/180/270 (MADCTL)
        invert=True,
        font_path="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        font_size=18,
        font_size_big=28,
        dim=0.85,             # 0..1
    ):
        self.WP = int(w_panel)
        self.HP = int(h_panel)

        self.rotate = int(rotate) % 360
        self.invert = bool(invert)

        self.DC = int(dc)
        self.RST = int(rst)
        self.CS = None if cs_gpio is None else int(cs_gpio)

        self.dim = float(dim)

        # Kolory (czarno-niebieskie)
        self.BG = (0, 0, 0)
        self.BLUE = self._mul((40, 120, 255), self.dim)   # neon blue
        self.BLUE2 = self._mul((15, 45, 95), self.dim)    # ciemniejszy
        self.TXT = self._mul((210, 225, 255), self.dim)
        self.SUB = self._mul((120, 145, 180), self.dim)
        self.GRID = self._mul((10, 25, 55), self.dim)

        # stan
        self.mode = "mic"  # "mic" / "bt"
        self.level = 0.0
        self.status = ""
        self.bt_connected = False
        self.bt_name = ""
        self.bt_addr = ""
        self.now = NowPlaying()

        # fonty
        try:
            self.font = ImageFont.truetype(font_path, font_size)
            self.font_big = ImageFont.truetype(font_path, font_size_big)
            self.font_small = ImageFont.truetype(font_path, 14)
        except Exception:
            self.font = ImageFont.load_default()
            self.font_big = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

        # GPIO (lgpio)
        self.gh = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self.gh, self.DC, 0)
        lgpio.gpio_claim_output(self.gh, self.RST, 1)
        if self.CS is not None:
            lgpio.gpio_claim_output(self.gh, self.CS, 1)

        # SPI
        self.spi = spidev.SpiDev()
        self.spi.open(int(spi_bus), int(spi_dev))
        self.spi.max_speed_hz = int(spi_hz)
        self.spi.mode = 0

        self._init_st7789()
        self._fill_black()

    # ---------- public API ----------
    def set_mode(self, mode: str):
        self.mode = "bt" if str(mode).lower() == "bt" else "mic"

    def set_level(self, level01: float):
        x = float(level01)
        if x < 0.0: x = 0.0
        if x > 1.0: x = 1.0
        self.level = x

    def set_status(self, text: str):
        self.status = (text or "")[:34]

    def set_bt(self, *, connected: bool, device_name: str = "", device_addr: str = ""):
        self.bt_connected = bool(connected)
        self.bt_name = (device_name or "")[:26]
        self.bt_addr = (device_addr or "")[:26]

    def set_track(self, *, artist: str = "", title: str = ""):
        self.now = NowPlaying(artist=(artist or "")[:20], title=(title or "")[:20])

    def close(self):
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            lgpio.gpiochip_close(self.gh)
        except Exception:
            pass

    # ---------- low-level ----------
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
        # buf może być list/bytes/bytearray
        self.spi.writebytes(list(buf))
        self._cs_high()

    def _reset(self):
        self._w(self.RST, 1); time.sleep(0.02)
        self._w(self.RST, 0); time.sleep(0.05)
        self._w(self.RST, 1); time.sleep(0.12)

    def _madctl_for_rotate(self) -> int:
        # ST7789 MADCTL bits: MY=0x80 MX=0x40 MV=0x20 RGB/BGR=0x08
        # Dla większości modułów ST7789:
        # 0:   0x00
        # 90:  0x60 (MV|MX)
        # 180: 0xC0 (MX|MY)
        # 270: 0xA0 (MV|MY)
        r = self.rotate
        if r == 0:
            mad = 0x00
        elif r == 90:
            mad = 0x60
        elif r == 180:
            mad = 0xC0
        else:  # 270
            mad = 0xA0
        return mad

    def _init_st7789(self):
        self._reset()
        self._cmd(0x01); time.sleep(0.12)   # SWRESET
        self._cmd(0x11); time.sleep(0.12)   # SLPOUT

        self._cmd(0x3A); self._data([0x55]) # 16-bit

        self._cmd(0x36); self._data([self._madctl_for_rotate()])

        if self.invert:
            self._cmd(0x21)                 # INVON
        else:
            self._cmd(0x20)                 # INVOFF

        self._cmd(0x29); time.sleep(0.12)   # DISPON

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(0x2B)
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._cmd(0x2C)

    def _img_to_rgb565(self, img: Image.Image) -> bytearray:
        img = img.convert("RGB")
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

    def _display(self, img: Image.Image):
        if img.size != (self.WP, self.HP):
            img = img.resize((self.WP, self.HP))
        self._set_window(0, 0, self.WP - 1, self.HP - 1)
        buf = self._img_to_rgb565(img)

        self._w(self.DC, 1)
        self._cs_low()
        chunk = 4096
        for i in range(0, len(buf), chunk):
            self.spi.writebytes(buf[i:i + chunk])
        self._cs_high()

    def _fill_black(self):
        self._display(Image.new("RGB", (self.WP, self.HP), self.BG))

    @staticmethod
    def _clamp8(x: int) -> int:
        return 0 if x < 0 else (255 if x > 255 else x)

    def _mul(self, c, k):
        return (
            self._clamp8(int(c[0] * k)),
            self._clamp8(int(c[1] * k)),
            self._clamp8(int(c[2] * k)),
        )

    # ---------- render ----------
    def render(self):
        # Renderujemy BEZ rotacji w PIL:
        # obraz ma rozmiar panelu (240x320) i idzie 1:1 do RAM.
        img = Image.new("RGB", (self.WP, self.HP), self.BG)
        d = ImageDraw.Draw(img)

        # === header ===
        d.rectangle((6, 6, self.WP - 7, 62), outline=self.GRID, width=2)
        d.text((14, 14), "VISUALIZER", fill=self.TXT, font=self.font)
        if self.status:
            d.text((14, 38), self.status, fill=self.SUB, font=self.font_small)

        # === tabs ===
        ty0, ty1 = 74, 118
        def tab(x0, label, active):
            x1 = x0 + 98
            d.rectangle((x0, ty0, x1, ty1), outline=(self.BLUE if active else self.GRID), width=(3 if active else 2))
            d.text((x0 + 26, ty0 + 12), label, fill=(self.BLUE if active else self.SUB), font=self.font)

        tab(12, "MIC", self.mode == "mic")
        tab(128, "BT",  self.mode == "bt")

        # === main box ===
        d.rectangle((6, 130, self.WP - 7, self.HP - 7), outline=self.GRID, width=2)

        # tytuł trybu
        title = "MIC MODE" if self.mode == "mic" else "BT MODE"
        d.text((14, 142), title, fill=self.BLUE, font=self.font_big)

        # === level bar (poziomy, Nokia) ===
        bx0, by0 = 14, 190
        bw, bh = self.WP - 28, 18
        d.rectangle((bx0, by0, bx0 + bw, by0 + bh), outline=self.GRID, width=2)

        lvl = float(self.level)
        if lvl < 0.0: lvl = 0.0
        if lvl > 1.0: lvl = 1.0
        fill_w = int((bw - 4) * lvl)
        if fill_w > 0:
            d.rectangle((bx0 + 2, by0 + 2, bx0 + 2 + fill_w, by0 + bh - 2), fill=self.BLUE2)
            # “cap” jaśniejszy
            cap0 = max(bx0 + 2, bx0 + 2 + fill_w - 6)
            d.rectangle((cap0, by0 + 2, bx0 + 2 + fill_w, by0 + bh - 2), fill=self.BLUE)

        # === info ===
        ix, iy = 14, 220
        if self.mode == "mic":
            d.text((ix, iy), "Input: microphone", fill=self.TXT, font=self.font)
            d.text((ix, iy + 22), "Source: local", fill=self.SUB, font=self.font_small)
        else:
            st = "CONNECTED" if self.bt_connected else "IDLE"
            d.text((ix, iy), f"BT: {st}", fill=(self.BLUE if self.bt_connected else self.SUB), font=self.font)
            if self.bt_name:
                d.text((ix, iy + 22), self.bt_name, fill=self.TXT, font=self.font_small)
            if self.bt_addr:
                d.text((ix, iy + 40), self.bt_addr, fill=self.SUB, font=self.font_small)

            # now playing (krótko)
            line = ""
            if self.now.artist and self.now.title:
                line = f"{self.now.artist} - {self.now.title}"
            elif self.now.title:
                line = self.now.title
            elif self.now.artist:
                line = self.now.artist

            if line:
                if len(line) > 26:
                    line = line[:25] + "…"
                d.text((ix, iy + 66), "NOW:", fill=self.SUB, font=self.font_small)
                d.text((ix, iy + 84), line, fill=self.TXT, font=self.font_small)

        self._display(img)
