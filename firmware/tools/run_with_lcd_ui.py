# firmware/tools/run_lcd_ui_only.py
import time
import math
from firmware.ui.lcd_ui import LCDUI

def main():
    ui = LCDUI(
        dc=25, rst=24, cs=5,          # jak używasz CE0/CE1 -> cs=None
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=90,                    # jak źle: 270
        dim=0.85,
        invert=True,
        madctl_base=0x00,
        width=240, height=320,
    )

    try:
        t0 = time.monotonic()
        while True:
            t = time.monotonic() - t0

            if int(t) % 10 < 5:
                ui.set_mode("mic")
                ui.set_status("listening...")
            else:
                ui.set_mode("bt")
                ui.set_status("bt idle")
                ui.set_bt(connected=False, name="")

            ui.set_effect("bars")

            lvl = 0.10 + 0.85 * (max(0.0, math.sin(t * 1.7)) ** 2)
            ui.set_level(lvl)

            ui.render()
            time.sleep(1 / 20)
    finally:
        ui.close()

if __name__ == "__main__":
    main()
