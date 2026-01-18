# firmware/tools/test_visuals.py
# python3 -u -m firmware.tools.test_visuals

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
    params = [p for p in sig.parameters.keys() if p != "self"]

    name_map = {
        "port": port, "device": port, "tty": port,
        "baud": baud, "baudrate": baud, "rate": baud,
        "num_leds": num_leds, "n_leds": num_leds, "leds": num_leds, "count": num_leds,
        "w": w, "width": w,
        "h": h, "height": h,
    }

    kwargs = {p: name_map[p] for p in params if p in name_map and name_map[p] is not None}
    if not kwargs:
        raise TypeError(f"Nie potrafię dopasować argumentów. Sygnatura: {sig}")

    return DriverCls(**kwargs)


def push_frame(leds, frame):
    """
    Obsługuje różne API drivera:
    - jeśli show(frame) istnieje -> użyj
    - jeśli show() bez argów, szukaj metody która przyjmuje frame: set_frame / write / send / update / render / draw
    - fallback: jeśli ma atrybut buffer/pixels/frame, ustaw i wywołaj show()
    """
    # 1) show(frame) jeśli działa
    if hasattr(leds, "show"):
        try:
            sig = inspect.signature(leds.show)
            # signature for bound method: (frame) => 1 parameter
            if len(sig.parameters) == 1:
                leds.show(frame)
                return
        except Exception:
            pass

    # 2) szukaj metody przyjmującej frame
    candidates = ["set_frame", "write", "send", "update", "render", "draw", "set_pixels", "set"]
    for name in candidates:
        if hasattr(leds, name):
            fn = getattr(leds, name)
            if callable(fn):
                try:
                    sig = inspect.signature(fn)
                    if len(sig.parameters) == 1:  # bound => (frame)
                        fn(frame)
                        if hasattr(leds, "show") and callable(getattr(leds, "show")):
                            leds.show()
                        return
                except Exception:
                    # spróbuj wywołać bez inspekcji
                    try:
                        fn(frame)
                        if hasattr(leds, "show") and callable(getattr(leds, "show")):
                            leds.show()
                        return
                    except Exception:
                        pass

    # 3) atrybut bufora + show()
    for attr in ["frame", "buffer", "pixels", "leds"]:
        if hasattr(leds, attr):
            try:
                setattr(leds, attr, frame)
                if hasattr(leds, "show") and callable(getattr(leds, "show")):
                    leds.show()
                    return
            except Exception:
                pass

    # 4) nie znaleziono – pokaż metody żebyś mi wkleił 1 linijkę
    names = [n for n in dir(leds) if not n.startswith("_")]
    raise RuntimeError(
        "Nie mogę wysłać frame do Esp32SerialDriver.\n"
        "Twoje show() jest bez argumentów, ale nie widzę metody typu set_frame/write/send.\n"
        f"Dostępne publiczne nazwy: {names}"
    )


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
    leds = make_driver(Esp32SerialDriver, port=PORT, baud=BAUD, num_leds=NUM_LEDS, w=W, h=H)

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    import sounddevice as sd
    block = fe.nfft
    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
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
        x = x[:, 0].astype(np.float32)

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
