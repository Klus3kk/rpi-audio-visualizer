from PIL import Image, ImageDraw
from firmware.ui.lcd_st7789 import LcdSt7789

lcd = LcdSt7789(width=240, height=320, dc=25, rst=24, cs=5, rotate=0)

img = Image.new("RGB", (lcd.w, lcd.h), "white")
d = ImageDraw.Draw(img)
d.text((20, 20), "LCD OK", fill="black")
lcd.dev.display(img)
