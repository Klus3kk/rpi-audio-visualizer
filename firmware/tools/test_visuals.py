# firmware/tools/test_visuals.py
# python3 -u -m firmware.tools.test_visuals

import time
import numpy as np
import sounddevice as sd

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

SWITCH_EVERY_S = 5.0
FPS = 40.0
DT_TARGET = 1.0 / FPS


def push_frame(leds: Esp32SerialDriver, frame):
    # frame: list[(r,g,b)] len == NUM_LEDS
    for i, rgb in enumerate(frame):
        leds.set_pixel(i, rgb)
    leds.show()


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
    # Twoj driver: show() bez argów, więc ładujemy przez set_pixel()
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    block = fe.nfft
    stream = sd.InputStream(
        samplerate=fe.sr,
        channels=1,
        blocksize=block,
        dtype="float32",
    )
    stream.start()

    effects = make_effects()
    params = {"intensity": 0.75, "color_mode": "auto"}

    i = 0
    name, eff = effects[i]
    t_switch = time.monotonic() + SWITCH_EVERY_S

    print(f"[tester] start -> {name}")

    last = time.monotonic()
    while True:
        now = time.monotonic()
        dt = now - last
        last = now

        if now >= t_switch:
            i = (i + 1) % len(effects)
            name, eff = effects[i]
            t_switch = now + SWITCH_EVERY_S
            print(f"[tester] -> {name}")

        x, _ = stream.read(block)
        x = x[:, 0].astype(np.float32, copy=False)

        features = fe.compute(x)

        try:
            frame = eff.update(features, dt, params)
        except TypeError:
            frame = eff.update(features, dt)

        if len(frame) != NUM_LEDS:
            frame = list(frame)
            if len(frame) != NUM_LEDS:
                raise RuntimeError(f"{name}: frame len {len(frame)} != {NUM_LEDS}")

        push_frame(leds, frame)

        sleep = DT_TARGET - (time.monotonic() - now)
        if sleep > 0:
            time.sleep(sleep)


if __name__ == "__main__":
    main()
