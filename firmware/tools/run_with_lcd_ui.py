# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import numpy as np
import sounddevice as sd

from firmware.ui.lcd_ui import LCDUI
from firmware.led.esp32_serial_driver import Esp32SerialDriver
from firmware.audio.features import FeatureExtractor

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.wave import WaveEffect


W, H = 16, 16
NUM_LEDS = W * H

PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS_LED = 40.0
DT_LED = 1.0 / FPS_LED

FPS_LCD = 10.0
DT_LCD = 1.0 / FPS_LCD


def push_frame(leds: Esp32SerialDriver, frame):
    # Esp32SerialDriver ma set_pixel(i,rgb) + show()
    # więc kopiujemy frame do bufora i show()
    for i, rgb in enumerate(frame):
        leds.set_pixel(i, rgb)
    leds.show()


def make_effects(w=W, h=H):
    return [
        ("bars", BarsEffect(w=w, h=h)),
        ("osc", OscilloscopeEffect(w=w, h=h)),
        ("radial", RadialPulseEffect(w=w, h=h)),
        ("fire", SpectralFireEffect(w=w, h=h)),
        ("vu", VUMeterEffect(w=w, h=h)),
        ("wave", WaveEffect(w=w, h=h)),
    ]


def main():
    # LCD (luma)
    ui = LCDUI({
        "width": 240,
        "height": 320,
        "spi_port": 0,
        "spi_device": 0,
        "dc": 25,
        "rst": 24,
        "cs": 5,        # jeśli u Ciebie tak działało
        "rotate": 1,    # 90deg => poziomo
        "spi_hz": 32_000_000,
    })

    # LED driver (ESP32)
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    # Audio
    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)
    block = fe.nfft
    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
    stream.start()

    effects = make_effects()
    idx = 0
    name, eff = effects[idx]

    # Stan UI (tylko MIC/BT)
    mode = "MIC"
    bt_connected = False

    params = {
        "intensity": 0.75,
        "color_mode": "auto",
        "power": 0.65,   # globalnie przytnij moc efektów jeśli chcesz
        "glow": 0.25,
    }

    t_prev = time.monotonic()
    t_lcd = 0.0

    try:
        while True:
            now = time.monotonic()
            dt = now - t_prev
            t_prev = now

            # audio -> features
            x, _ = stream.read(block)
            x = x[:, 0].astype(np.float32)
            feats = fe.compute(x)

            # efekt -> frame
            try:
                frame = eff.update(feats, dt, params)
            except TypeError:
                frame = eff.update(feats, dt)

            if len(frame) != NUM_LEDS:
                frame = list(frame)
                if len(frame) != NUM_LEDS:
                    raise RuntimeError(f"{name}: frame len {len(frame)} != {NUM_LEDS}")

            # LED @ 40 FPS
            push_frame(leds, frame)

            # LCD @ 10 FPS (żeby nie lagowało)
            t_lcd += dt
            if t_lcd >= DT_LCD:
                t_lcd = 0.0
                ui.render(
                    mode=mode,
                    effect=name,
                    feats=feats,
                    bt_connected=bt_connected,
                    nowp={"artist": "", "title": ""}  # jak potem dodasz BT appkę, tu wstawisz now playing
                )

            # utrzymanie FPS
            sleep = DT_LED - (time.monotonic() - now)
            if sleep > 0:
                time.sleep(sleep)

    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        try:
            leds.clear()
            leds.close()
        except Exception:
            pass
        try:
            ui.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
