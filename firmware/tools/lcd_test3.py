from firmware.ui.lcd_st7789 import LcdSt7789
from PIL import Image

lcd = LcdSt7789(dc=25, rst=24, cs_gpio=5, rotate=90, invert=True, madctl_base=0x00)
lcd.fill((255,0,0)); input("red")
lcd.fill((0,255,0)); input("green")
lcd.fill((0,0,255)); input("blue")
lcd.close()
