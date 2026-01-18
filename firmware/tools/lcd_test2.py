#!/usr/bin/env python3
import time
import spidev
import lgpio
from PIL import Image, ImageDraw, ImageFont

# Twoje piny (BCM):
DC  = 25
RST = 24

# CS:
# - jeśli używasz SPI CE0/CE1 -> ustaw CS = None i wybierz SPI_DEV 0/1
# - jeśli naprawdę masz CS na GPIO5 -> ustaw CS = 5 (ręcznie sterowane)
CS = 5  # lub None

SPI_BUS = 0
SPI_DEV = 0
SPI_HZ  = 24_000_000   # zacznij od 24MHz (40MHz bywa za ostre)

W, H = 240, 320

# --- lgpio helpers ---
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
    data(h, spi, [0x55])  # 16-bit color

    cmd(h, spi, 0x36)  # MADCTL
    data(h, spi, [0x00])  # na start

    cmd(h, spi, 0x21)  # INVON (często potrzebne)
    time.sleep(0.01)

    cmd(h, spi, 0x29)  # DISPON
    time.sleep(0.12)

def set_window(h, spi, x0, y0, x1, y1):
    cmd(h, spi, 0x2A)  # CASET
    data(h, spi, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
    cmd(h, spi, 0x2B)  # RASET
    data(h, spi, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
    cmd(h, spi, 0x2C)  # RAMWR

def img_to_rgb565_bytes(img):
    img = img.convert("RGB")
    px = img.load()
    out = bytearray(W * H * 2)
    i = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = (v >> 8) & 0xFF
            out[i+1] = v & 0xFF
            i += 2
    return out

def display(h, spi, img):
    set_window(h, spi, 0, 0, W-1, H-1)
    buf = img_to_rgb565_bytes(img)
    gpio_write(h, DC, 1)
    cs_low(h)
    chunk = 4096
    for i in range(0, len(buf), chunk):
        spi.writebytes(buf[i:i+chunk])
    cs_high(h)

def main():
    gh = gpio_open(0)

    # GPIO outputs
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

        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        d.text((20, 20), "LCD OK (lgpio)", fill=(0, 0, 0), font=font)
        d.text((20, 45), f"SPI={SPI_BUS}.{SPI_DEV} DC={DC} RST={RST} CS={CS}", fill=(0,0,0), font=font)
        d.text((20, 70), f"SPI_HZ={SPI_HZ}", fill=(0,0,0), font=font)

        display(gh, spi, img)
        time.sleep(10)

    finally:
        spi.close()
        gpio_close(gh)

if __name__ == "__main__":
    main()
