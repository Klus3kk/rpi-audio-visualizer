# firmware/tools/test_visuals.py
# Uruchom:
#   python3 -u -m firmware.tools.test_visuals

import time
import inspect
import numpy as np

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


def make_driver(DriverCls, *, port, baud, num_leds, w=None, h=None):
    sig = inspect.signature(DriverCls.__init__)
    params = list(sig.parameters.keys())
    if params and params[0] == "self":
        params = params[1:]

    name_map = {
        "port": port, "device": port, "tty": port,
        "baud": baud, "baudrate": baud, "rate": baud,
        "num_leds": num_leds, "n_leds": num_leds, "leds": num_leds, "count": num_leds,
        "w": w, "width": w,
        "h": h, "height": h,
    }

    kwargs = {}
    for p in params:
        if p in name_map and name_map[p] is not None:
            kwargs[p] = name_map[p]

    if not kwargs:
        raise TypeError(f"Nie potrafię dopasować argumentów. Sygnatura: {sig}")

    return DriverCls(**kwargs)


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
    # --- LED driver (bez konfliktów argumentów)
    leds = make_driver(Esp32SerialDriver, port=PORT, baud=BAUD, num_leds=NUM_LEDS, w=W, h=H)

    # --- FeatureExtractor: on potrzebuje surowych próbek audio x
    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    # --- Audio input (sounddevice)
    import sounddevice as sd

    block = fe.nfft  # dokładnie tyle próbek ile FFT
    stream = sd.InputStream(
        samplerate=fe.sr,
        channels=1,
        blocksize=block,
        dtype="float32",
    )
    stream.start()

    effects = make_effects()
    params = {"intensity": 0.75, "color_mode": "auto"}

    idx = 0
    cur_name, cur = effects[idx]
    t_switch = time.monotonic() + SWITCH_EVERY_S

    print(f"[tester] start -> {cur_name}")

    last = time.monotonic()
    while True:
        now = time.monotonic()
        dt = now - last
        last = now

        if now >= t_switch:
            idx = (idx + 1) % len(effects)
            cur_name, cur = effects[idx]
            t_switch = now + SWITCH_EVERY_S
            print(f"[tester] -> {cur_name}")

        # czytaj audio -> x
        x, _ = stream.read(block)          # (block, 1)
        x = x[:, 0].astype(np.float32)     # (block,)

        # features z Twojego FE
        features = fe.compute(x)

        # efekt -> frame
        try:
            frame = cur.update(features, dt, params)
        except TypeError:
            frame = cur.update(features, dt)

        if len(frame) != NUM_LEDS:
            frame = list(frame)
            if len(frame) != NUM_LEDS:
                raise RuntimeError(f"{cur_name}: frame len {len(frame)} != {NUM_LEDS}")

        leds.show(frame)

        sleep = DT_TARGET - (time.monotonic() - now)
        if sleep > 0:
            time.sleep(sleep)


if __name__ == "__main__":
    main()
