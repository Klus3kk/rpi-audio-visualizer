#!/usr/bin/env python3
import time
import spidev
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

# Twoje piny:
DC  = 25
RST = 24
# CS: jeżeli naprawdę używasz GPIO5 jako CS, to tu ustaw 5 i steruj ręcznie.
# Jeżeli masz CS na CE0/CE1, ustaw CS=None i wybierz spi_device 0 lub 1.
CS = 5  # ustaw na None jeśli używasz CE0/CE1

SPI_BUS = 0
SPI_DEV = 0   # 0 => /dev/spidev0.0, 1 => /dev/spidev0.1
SPI_HZ  = 40_000_000  # możesz zjechać do 24_000_000 jeśli będą artefakty

W, H = 240, 320

def gpio_setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(DC, GPIO.OUT)
    GPIO.setup(RST, GPIO.OUT)
    if CS is not None:
        GPIO.setup(CS, GPIO.OUT)
        GPIO.output(CS, 1)

def cs_low():
    if CS is not None:
        GPIO.output(CS, 0)

def cs_high():
    if CS is not None:
        GPIO.output(CS, 1)

def cmd(spi, c):
    GPIO.output(DC, 0)
    cs_low()
    spi.writebytes([c])
    cs_high()

def data(spi, buf):
    GPIO.output(DC, 1)
    cs_low()
    spi.writebytes(buf)
    cs_high()

def reset():
    GPIO.output(RST, 1)
    time.sleep(0.05)
    GPIO.output(RST, 0)
    time.sleep(0.05)
    GPIO.output(RST, 1)
    time.sleep(0.12)

def init_st7789(spi):
    reset()

    cmd(spi, 0x01)  # SWRESET
    time.sleep(0.12)
    cmd(spi, 0x11)  # SLPOUT
    time.sleep(0.12)

    cmd(spi, 0x3A)  # COLMOD
    data(spi, [0x55])  # 16-bit color

    cmd(spi, 0x36)  # MADCTL
    # 0x00 = domyślnie. Jeśli rotacja/odwrócenie złe, zmienimy.
    data(spi, [0x00])

    cmd(spi, 0x21)  # INVON (często potrzebne na modułach ST7789)
    time.sleep(0.01)

    cmd(spi, 0x29)  # DISPON
    time.sleep(0.12)

def set_window(spi, x0, y0, x1, y1):
    cmd(spi, 0x2A)  # CASET
    data(spi, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])

    cmd(spi, 0x2B)  # RASET
    data(spi, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])

    cmd(spi, 0x2C)  # RAMWR

def img_to_rgb565_bytes(img):
    # img RGB -> rgb565 big-endian
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

def display(spi, img):
    set_window(spi, 0, 0, W-1, H-1)
    buf = img_to_rgb565_bytes(img)
    GPIO.output(DC, 1)
    cs_low()
    # wysyłka w kawałkach, żeby nie zabić pamięci
    chunk = 4096
    for i in range(0, len(buf), chunk):
        spi.writebytes(buf[i:i+chunk])
    cs_high()

def main():
    gpio_setup()
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEV)
    spi.max_speed_hz = SPI_HZ
    spi.mode = 0

    try:
        init_st7789(spi)

        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        d.text((20, 20), "LCD OK (no luma)", fill=(0, 0, 0), font=font)
        d.text((20, 45), f"SPI={SPI_BUS}.{SPI_DEV} DC={DC} RST={RST} CS={CS}", fill=(0,0,0), font=font)

        display(spi, img)
        time.sleep(10)

    finally:
        spi.close()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
