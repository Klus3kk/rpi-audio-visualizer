import time
from firmware.led.leds0_driver import Leds0Driver

leds = Leds0Driver(num_leds=256)

try:
    leds.fill((255, 0, 0))
    leds.show()
    time.sleep(1)

    leds.fill((0, 255, 0))
    leds.show()
    time.sleep(1)

    leds.fill((0, 0, 255))
    leds.show()
    time.sleep(1)

    leds.fill((255, 255, 255))
    leds.show()
    time.sleep(1)

    leds.clear()
finally:
    leds.close()
