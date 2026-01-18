# firmware/tools/run_lcd_ui_only.py
import time
import math
from firmware.ui.lcd_ui import LCDUI

def main():
    ui = LCDUI(
        dc=25, rst=24, cs=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=90,  # jeśli źle: 270
        dim=0.75,
    )

    try:
        mode = "mic"
        t0 = time.monotonic()
        last = t0
        while True:
            now = time.monotonic()
            t = now - t0

            # demo: toggle co 5s
            if int(t) % 10 < 5:
                mode = "mic"
                ui.set_status("listening...")
            else:
                mode = "bt"
                ui.set_status("bt idle")

            ui.set_mode(mode)

            # demo level
            lvl = 0.15 + 0.8 * (max(0.0, math.sin(t*1.8))**2)
            ui.set_level(lvl)

            ui.render()
            time.sleep(1/20)
    finally:
        ui.close()

if __name__ == "__main__":
    main()
