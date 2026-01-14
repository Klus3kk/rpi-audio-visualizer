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

    def render_status(self, state, feats):
        img = Image.new("RGB", (self.w, self.h), "black")
        d = ImageDraw.Draw(img)

        d.text((10, 10), f"MODE: {state.mode}", font=self.font, fill="white")
        d.text((10, 30), f"EFFECT: {state.effect}", font=self.font, fill="white")
        d.text((10, 50), f"BRI: {state.brightness:.2f}", font=self.font, fill="white")

        d.text((10, 90), f"RMS: {feats['rms']:.4f}", font=self.font, fill="white")
        d.text((10, 110), f"BASS: {feats['bass']:.2f}", font=self.font, fill="white")
        d.text((10, 130), f"MID: {feats['mid']:.2f}", font=self.font, fill="white")
        d.text((10, 150), f"TREBLE: {feats['treble']:.2f}", font=self.font, fill="white")

        self.dev.display(img)
