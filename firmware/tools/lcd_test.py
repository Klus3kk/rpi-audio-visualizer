#!/usr/bin/env python3
import time
import spidev
import lgpio
from PIL import Image, ImageDraw, ImageFont

# ====== PINS (BCM) ======
DC  = 25
RST = 24
CS  = 5        # ustaw None jeśli używasz CE0/CE1 sprzętowo
SPI_BUS = 0
SPI_DEV = 0
SPI_HZ  = 24_000_000

# ====== PANEL ======
W_PORTRAIT, H_PORTRAIT = 240, 320
# Landscape output size (rotacja 90°): 320x240
W, H = 320, 240

# ====== THEME (neon blue on black) ======
BG      = (0, 0, 0)
NEON    = (0, 180, 255)   # główny neon
NEON2   = (0, 90, 180)    # przygaszony
WHITE   = (240, 245, 255)
GRAY    = (90, 105, 120)
CARD    = (8, 12, 18)

def gpio_open(chip=0):
    return lgpio.gpiochip_open(chip)

def gpio_out(h, pin, val=0):
    lgpio.gpio_claim_output(h, pin, val)

def gpio_write(h, pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

def gpio_close(h):
    lgpio.gpiochip_close(h)

def cs_low(h):
    if CS is not None:
        gpio_write(h, CS, 0)

def cs_high(h):
    if CS is not None:
        gpio_write(h, CS, 1)

def cmd(h, spi, c):
    gpio_write(h, DC, 0)
    cs_low(h)
    spi.writebytes([c])
    cs_high(h)

def data(h, spi, buf):
    gpio_write(h, DC, 1)
    cs_low(h)
    spi.writebytes(buf)
    cs_high(h)

def reset(h):
    gpio_write(h, RST, 1); time.sleep(0.05)
    gpio_write(h, RST, 0); time.sleep(0.05)
    gpio_write(h, RST, 1); time.sleep(0.12)

def init_st7789(h, spi):
    reset(h)

    cmd(h, spi, 0x01)  # SWRESET
    time.sleep(0.12)
    cmd(h, spi, 0x11)  # SLPOUT
    time.sleep(0.12)

    cmd(h, spi, 0x3A)  # COLMOD
    data(h, spi, [0x55])  # 16-bit

    cmd(h, spi, 0x36)  # MADCTL
    # Twoje wartości mogą wymagać zmiany, ale skoro "wykrywa" i działa,
    # zostawiamy na start 0x00 i robimy rotację w PIL (rotate).
    data(h, spi, [0x00])

    cmd(h, spi, 0x21)  # INVON
    time.sleep(0.01)

    cmd(h, spi, 0x29)  # DISPON
    time.sleep(0.12)

def set_window(h, spi, x0, y0, x1, y1):
    cmd(h, spi, 0x2A)  # CASET
    data(h, spi, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
    cmd(h, spi, 0x2B)  # RASET
    data(h, spi, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
    cmd(h, spi, 0x2C)  # RAMWR

def img_to_rgb565_bytes(img_240x320):
    img = img_240x320.convert("RGB")
    px = img.load()
    out = bytearray(W_PORTRAIT * H_PORTRAIT * 2)
    i = 0
    for y in range(H_PORTRAIT):
        for x in range(W_PORTRAIT):
            r, g, b = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = (v >> 8) & 0xFF
            out[i+1] = v & 0xFF
            i += 2
    return out

def display(h, spi, img_240x320):
    set_window(h, spi, 0, 0, W_PORTRAIT-1, H_PORTRAIT-1)
    buf = img_to_rgb565_bytes(img_240x320)
    gpio_write(h, DC, 1)
    cs_low(h)
    chunk = 4096
    for i in range(0, len(buf), chunk):
        spi.writebytes(buf[i:i+chunk])
    cs_high(h)

def rr(draw, xy, r, fill=None, outline=None, w=1):
    # rounded rectangle helper
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=w)

def neon_line(draw, x0, y0, x1, y1):
    # prosta „poświata”
    draw.line((x0,y0,x1,y1), fill=NEON2, width=3)
    draw.line((x0,y0,x1,y1), fill=NEON,  width=1)

def draw_ui(mode, status, level, t):
    """
    Renderuje LANDSCAPE 320x240 w PIL,
    potem obracamy do 240x320 żeby wysłać na panel.
    """
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    font = ImageFont.load_default()

    # Header
    rr(d, (10, 10, W-10, 54), r=14, fill=CARD, outline=(0, 35, 55), w=2)
    d.text((18, 18), "PixTrick Visualizer", fill=WHITE, font=font)
    d.text((18, 34), status, fill=GRAY, font=font)

    # Mode pills
    pill_y = 66
    def pill(x, label, active):
        w0 = 96
        rr(d, (x, pill_y, x+w0, pill_y+34), r=12,
           fill=(0, 0, 0) if active else CARD,
           outline=NEON if active else (0,35,55),
           w=2)
        d.text((x+12, pill_y+10), label, fill=NEON if active else GRAY, font=font)

    pill(10, "MIC", mode == "mic")
    pill(112, "BT", mode == "bt")

    # Right side: small neon badge
    rr(d, (W-110, pill_y, W-10, pill_y+34), r=12, fill=CARD, outline=(0,35,55), w=2)
    d.text((W-100, pill_y+10), "LIVE", fill=NEON, font=font)

    # Main card
    rr(d, (10, 110, W-10, H-10), r=18, fill=CARD, outline=(0,35,55), w=2)

    # Neon separator line
    neon_line(d, 18, 150, W-18, 150)

    # Left: level meter
    d.text((20, 120), "Input level", fill=GRAY, font=font)
    meter_x0, meter_y0 = 20, 160
    meter_x1, meter_y1 = 60, H-22
    rr(d, (meter_x0, meter_y0, meter_x1, meter_y1), r=10, fill=(0,0,0), outline=(0,35,55), w=2)

    # fill bar
    level = max(0.0, min(1.0, float(level)))
    fy = int(meter_y1 - level * (meter_y1 - meter_y0))
    rr(d, (meter_x0+4, fy, meter_x1-4, meter_y1-4), r=8, fill=NEON2, outline=None, w=0)
    # glow top
    d.rectangle((meter_x0+4, fy, meter_x1-4, min(meter_y1, fy+6)), fill=NEON)

    # Center: big mode label
    big = "MIC MODE" if mode == "mic" else "BLUETOOTH MODE"
    d.text((80, 170), big, fill=WHITE, font=font)

    # Bottom hint
    hint = "MIC: live audio" if mode == "mic" else "BT: app / devices"
    d.text((80, 190), hint, fill=GRAY, font=font)

    # Tiny animated neon dot
    dot_x = 80 + int(18 * (0.5 + 0.5 * __import__("math").sin(t*3.0)))
    rr(d, (dot_x, 212, dot_x+10, 222), r=5, fill=NEON, outline=None, w=0)

    return img

def main():
    gh = gpio_open(0)
    gpio_out(gh, DC, 0)
    gpio_out(gh, RST, 1)
    if CS is not None:
        gpio_out(gh, CS, 1)

    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEV)
    spi.max_speed_hz = SPI_HZ
    spi.mode = 0

    try:
        init_st7789(gh, spi)

        mode = "mic"
        t0 = time.monotonic()
        last_switch = t0
        status = "Ready"

        while True:
            now = time.monotonic()
            t = now - t0

            # demo: przełącz tryb co 5s (potem podepniesz pod real state)
            if now - last_switch > 5.0:
                mode = "bt" if mode == "mic" else "mic"
                last_switch = now
                status = "BT scanning..." if mode == "bt" else "Listening..."

            # demo: fake level (zastąpisz RMS)
            import math
            level = 0.15 + 0.75 * max(0.0, math.sin(t*1.7))**2

            ui_land = draw_ui(mode=mode, status=status, level=level, t=t)

            # LANDSCAPE 320x240 -> panel 240x320
            # rotate=90 lub 270 zależnie od montażu
            ui_portrait = ui_land.rotate(90, expand=True)

            # sanity: po rotate musi być 240x320
            if ui_portrait.size != (W_PORTRAIT, H_PORTRAIT):
                ui_portrait = ui_portrait.resize((W_PORTRAIT, H_PORTRAIT))

            display(gh, spi, ui_portrait)
            time.sleep(1/20)

    finally:
        spi.close()
        gpio_close(gh)

if __name__ == "__main__":
    main()
