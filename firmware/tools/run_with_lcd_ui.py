# firmware/tools/run_with_lcd_ui.py
import time
import math
from firmware.ui.lcd_ui import LCDUI


def main():
    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=90,          # 90 albo 270
        mirror=True,        # <-- TU masz "invert na druga stronę"
        panel_invert=False, # <-- jeśli tło było białe, to to ma być False
        dim=0.85,
    )

    try:
        t0 = time.monotonic()
        while True:
            t = time.monotonic() - t0

            # --- DEMO przełączania trybu co 6s ---
            if int(t) % 12 < 6:
                ui.set_mode("mic")
                ui.set_status("mic listening")
                ui.set_effect("bars")
                ui.set_visual_params(intensity=0.75, color_mode="auto")

                # demo-features
                rms = 0.02 + 0.05 * (max(0.0, math.sin(t * 1.3)) ** 2)
                ui.set_mic_feats(rms=rms, bass=0.35, mid=0.22, treble=0.15)

            else:
                ui.set_mode("bt")
                ui.set_status("bt ready")
                ui.set_effect("spectral_fire")
                ui.set_visual_params(intensity=0.65, color_mode="auto")

                # demo-bt + track
                ui.set_bt(connected=True, device_name="VisualizerApp", device_addr="AA:BB:CC:DD:EE:FF")
                ui.set_track(artist="Weyes Blood", title="Andromeda")

            ui.render()
            time.sleep(1 / 15)  # LCD: 10-20 FPS wystarczy
    finally:
        ui.close()


if __name__ == "__main__":
    main()
