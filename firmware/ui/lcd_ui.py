# firmware/ui/lcd_ui.py
import time
import math
import spidev
import lgpio
from PIL import Image, ImageDraw, ImageFont

class LCDUI:
    """
    Nokia-like UI (kanciaste, czarne tło, neon-cyan).
    Tylko 2 tryby: MIC / BT.
    Render: landscape 320x240 -> rotate -> panel 240x320.
    """

    def __init__(
        self,
        *,
        spi_bus=0,
        spi_dev=0,
        spi_hz=24_000_000,
        dc=25,
        rst=24,
        cs=5,                 # None jeśli sprzętowy CE0/CE1
        rotate=90,            # 90 albo 270
        w_panel=240,
        h_panel=320,
        font_path="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        font_size=18,
        font_size_big=28,
        accent=(0, 180, 255),
        bg=(0, 0, 0),
        dim=0.75,             # global “moc” UI (0..1) - przyciemnia kolory
    ):
        self.spi_bus = int(spi_bus)
        self.spi_dev = int(spi_dev)
        self.spi_hz = int(spi_hz)
        self.DC = int(dc)
        self.RST = int(rst)
        self.CS = None if cs is None else int(cs)

        self.rotate = int(rotate)
        self.WP = int(w_panel)
        self.HP = int(h_panel)

        # landscape canvas
        self.W = 320
        self.H = 240

        self.bg = tuple(bg)
        self.accent = tuple(accent)
        self.dim = float(dim)

        # state
        self.mode = "mic"   # "mic" / "bt"
        self.level = 0.0    # 0..1
        self.status = ""    # krótka linia
        self._t0 = time.monotonic()

        # fonts
        try:
            self.font = ImageFont.truetype(font_path, font_size)
            self.font_big = ImageFont.truetype(font_path, font_size_big)
        except Exception:
            self.font = ImageFont.load_default()
            self.font_big = ImageFont.load_default()

        # gpio/spi
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

    # ---------------- HW helpers ----------------
    def _w(self, pin, val):
        lgpio.gpio_write(self.gh, pin, 1 if val else 0)

    def _cs_low(self):
        if self.CS is not None:
            self._w(self.CS, 0)

    def _cs_high(self):
        if self.CS is not None:
            self._w(self.CS, 1)

    def _cmd(self, c):
        self._w(self.DC, 0)
        self._cs_low()
        self.spi.writebytes([c])
        self._cs_high()

    def _data(self, buf):
        self._w(self.DC, 1)
        self._cs_low()
        self.spi.writebytes(buf)
        self._cs_high()

    def _reset(self):
        self._w(self.RST, 1); time.sleep(0.05)
        self._w(self.RST, 0); time.sleep(0.05)
        self._w(self.RST, 1); time.sleep(0.12)

    def _init_st7789(self):
        self._reset()
        self._cmd(0x01); time.sleep(0.12)  # SWRESET
        self._cmd(0x11); time.sleep(0.12)  # SLPOUT

        self._cmd(0x3A); self._data([0x55])  # 16-bit

        self._cmd(0x36); self._data([0x00])  # MADCTL (zostaw)
        self._cmd(0x21); time.sleep(0.01)    # INVON
        self._cmd(0x29); time.sleep(0.12)    # DISPON

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(0x2B)
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._cmd(0x2C)

    def _img_to_rgb565(self, img):
        img = img.convert("RGB")
        px = img.load()
        out = bytearray(self.WP * self.HP * 2)
        i = 0
        for y in range(self.HP):
            for x in range(self.WP):
                r, g, b = px[x, y]
                v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                out[i] = (v >> 8) & 0xFF
                out[i+1] = v & 0xFF
                i += 2
        return out

    def _display(self, img240x320):
        self._set_window(0, 0, self.WP-1, self.HP-1)
        buf = self._img_to_rgb565(img240x320)
        self._w(self.DC, 1)
        self._cs_low()
        chunk = 4096
        for i in range(0, len(buf), chunk):
            self.spi.writebytes(buf[i:i+chunk])
        self._cs_high()

    # ---------------- public API ----------------
    def set_mode(self, mode: str):
        self.mode = "bt" if str(mode).lower() == "bt" else "mic"

    def set_level(self, level01: float):
        x = float(level01)
        if x < 0.0: x = 0.0
        if x > 1.0: x = 1.0
        self.level = x

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

    # ---------------- drawing ----------------
    def _mul(self, c, k):
        return (int(c[0]*k), int(c[1]*k), int(c[2]*k))

    def render(self):
        t = time.monotonic() - self._t0

        ACC = self._mul(self.accent, self.dim)
        ACC2 = self._mul(self.accent, self.dim*0.45)
        TXT = self._mul((230, 240, 255), self.dim)
        SUB = self._mul((110, 130, 150), self.dim)
        GRID = self._mul((0, 55, 80), self.dim)

        img = Image.new("RGB", (self.W, self.H), self.bg)
        d = ImageDraw.Draw(img)

        # top bar (kanciaste)
        d.rectangle((0, 0, self.W-1, 42), fill=(0,0,0), outline=GRID, width=2)
        d.text((10, 8), "VISUALIZER", fill=TXT, font=self.font)
        if self.status:
            d.text((10, 24), self.status, fill=SUB, font=self.font)

        # mode tabs
        tab_y0, tab_y1 = 54, 92
        def tab(x0, label, active):
            x1 = x0 + 94
            d.rectangle((x0, tab_y0, x1, tab_y1),
                        fill=(0,0,0),
                        outline=(ACC if active else GRID),
                        width=(3 if active else 2))
            d.text((x0+14, tab_y0+12), label, fill=(ACC if active else SUB), font=self.font)

        tab(10,  "MIC", self.mode == "mic")
        tab(112, "BT",  self.mode == "bt")

        # main panel
        d.rectangle((10, 104, self.W-10, self.H-10), fill=(0,0,0), outline=GRID, width=2)

        # big mode label
        label = "MIC MODE" if self.mode == "mic" else "BT MODE"
        d.text((24, 118), label, fill=ACC, font=self.font_big)

        # level meter (vertical)
        mx0, my0, mx1, my1 = 24, 160, 68, self.H-22
        d.rectangle((mx0, my0, mx1, my1), fill=(0,0,0), outline=GRID, width=2)

        # fill (neon)
        lvl = self.level
        fy = int(my1 - lvl * (my1 - my0))
        if fy < my1:
            d.rectangle((mx0+3, fy, mx1-3, my1-3), fill=ACC2, outline=None)
            d.rectangle((mx0+3, fy, mx1-3, min(my1-3, fy+6)), fill=ACC, outline=None)

        # simple “scanline” / accent line
        yline = 150
        d.line((24, yline, self.W-24, yline), fill=ACC2, width=2)
        d.line((24, yline+1, self.W-24, yline+1), fill=ACC, width=1)

        # small activity dot
        dot_x = 240 + int(20 * (0.5 + 0.5*math.sin(t*3.0)))
        d.rectangle((dot_x, 206, dot_x+10, 216), fill=ACC, outline=None)

        # rotate to panel orientation
        out = img.rotate(self.rotate, expand=True)  # -> 240x320
        if out.size != (self.WP, self.HP):
            out = out.resize((self.WP, self.HP))
        self._display(out)
