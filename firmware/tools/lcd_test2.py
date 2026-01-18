from PIL import Image, ImageDraw, ImageFont
from firmware.ui.lcd_st7789 import LcdSt7789
import time

lcd = LcdSt7789(width=240, height=320, dc=25, rst=24, cs=5, spi_bus=0, spi_dev=0, spi_hz=24_000_000, invert=True, madctl=0x60)

img = Image.new("RGB", (240, 320), (0,0,0))
d = ImageDraw.Draw(img)
d.text((10,10), "LCD OK", fill=(0,180,255), font=ImageFont.load_default())
lcd.display(img)
time.sleep(10)
lcd.close()
