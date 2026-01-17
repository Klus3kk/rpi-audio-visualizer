import time
from firmware.led.esp32_serial_driver import Esp32SerialDriver

led = Esp32SerialDriver(port="/dev/ttyUSB0", baud=921600, num_leds=256)
try:
    led.fill((255, 0, 0)); led.show(); time.sleep(1)
    led.fill((0, 255, 0)); led.show(); time.sleep(1)
    led.fill((0, 0, 255)); led.show(); time.sleep(1)
    led.clear()
finally:
    led.close()
