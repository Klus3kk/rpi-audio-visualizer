# firmware/test_visualizations.py
# Uruchom:
#   python3 -u -m firmware.test_visualizations
#
# Co 5 sekund przełącza efekt i wysyła klatki na ESP32.

import time
import numpy as np

from firmware.led.esp32_serial_driver import Esp32SerialDriver
from firmware.audio.features import FeatureExtractor

# efekty
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

SWITCH_EVERY_S = 5.0
FPS = 40.0  # 25-60 ok
DT = 1.0 / FPS


def make_effects(w=W, h=H):
    return [
        ("bars", BarsEffect(w=w, h=h)),
        ("oscilloscope", OscilloscopeEffect(w=w, h=h)),
        ("radial_pulse", RadialPulseEffect(w=w, h=h)),
        ("spectral_fire", SpectralFireEffect(w=w, h=h)),
        ("vu_meter", VUMeterEffect(w=w, h=h)),
        ("wave", WaveEffect(w=w, h=h)),
    ]


def main():
    # jeśli Twój driver ma inną sygnaturę, to ustaw TYLKO positional albo TYLKO keyword.
    # Najbezpieczniej: port, baud, num_leds jako keyword:
    leds = Esp32SerialDriver(PORT, BAUD, num_leds=NUM_LEDS)

    fe = FeatureExtractor()  # zakładam że zwraca dict: rms, bands, samplerate, nfft, mag (opcjonalnie)
    effects = make_effects()

    params = {
        "intensity": 0.75,
        "color_mode": "auto",
        "power": 0.85,   # używane przez wave/palette, reszta może ignorować
        "glow": 0.30,    # wave
    }

    idx = 0
    cur_name, cur = effects[idx]
    t_switch = time.monotonic() + SWITCH_EVERY_S
    t_prev = time.monotonic()

    print(f"[tester] start -> {cur_name}")

    while True:
        now = time.monotonic()
        dt = now - t_prev
        t_prev = now

        # przełączanie efektu
        if now >= t_switch:
            idx = (idx + 1) % len(effects)
            cur_name, cur = effects[idx]
            t_switch = now + SWITCH_EVERY_S
            print(f"[tester] -> {cur_name}")

        # audio -> features
        features = fe.update(dt) if hasattr(fe, "update") else fe.get_features(dt)

        # efekt -> frame
        try:
            frame = cur.update(features, dt, params)  # większość Twoich efektów ma (features, dt, params)
        except TypeError:
            # fallback dla efektów bez params
            frame = cur.update(features, dt)

        # sanity: długość klatki
        if len(frame) != NUM_LEDS:
            # próbuj spłaszczyć jeśli ktoś zwróci np. ndarray
            frame = list(frame)
            if len(frame) != NUM_LEDS:
                raise RuntimeError(f"{cur_name}: frame len {len(frame)} != {NUM_LEDS}")

        # wysyłka do ESP
        leds.show(frame)

        # stały fps
        sleep = DT - (time.monotonic() - now)
        if sleep > 0:
            time.sleep(sleep)


if __name__ == "__main__":
    main()
