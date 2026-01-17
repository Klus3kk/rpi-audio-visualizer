import time
from firmware.led.esp32_serial_driver import EspSerialDriver

d = EspSerialDriver(port="/dev/ttyUSB0", baud=115200, debug=True)

try:
    d.fill((255,0,0)); d.show(); time.sleep(1)
    d.fill((0,255,0)); d.show(); time.sleep(1)
    d.fill((0,0,255)); d.show(); time.sleep(1)
    d.clear()
finally:
    d.close()
