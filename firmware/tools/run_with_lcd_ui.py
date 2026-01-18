# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import numpy as np
import sounddevice as sd

from firmware.audio.features import FeatureExtractor
from firmware.ui.lcd_ui import LCDUI, UIState

def main():
    # LCD config (LANDSCAPE)
    ui = LCDUI({
        "width_panel": 240,
        "height_panel": 320,
        "spi_bus": 0,
        "spi_dev": 0,          # spróbuj 1 jeśli masz na CE1
        "spi_hz": 24_000_000,
        "dc": 25,
        "rst": 24,
        # "bl": 23,            # odkomentuj jeśli BL jest na GPIO
        # "cs_gpio": 5,        # odkomentuj jeśli CS jest ręcznie na GPIO5
        "rotate": 90,
        "invert": True,
        "madctl_base": 0x00,
    })

    state = UIState(mode="MIC", effect="bars", intensity=0.75, brightness=0.25)

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)
    block = fe.nfft

    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
    stream.start()

    last = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            dt = now - last
            last = now

            x, _ = stream.read(block)
            x = x[:, 0].astype(np.float32)
            feats = fe.compute(x)

            ui.render(state, feats)

            # 20 FPS dla UI (żeby nie lagowało visuals)
            time.sleep(max(0.0, 0.05 - (time.monotonic() - now)))

    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        ui.close()

if __name__ == "__main__":
    main()
