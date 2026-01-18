# firmware/tools/test_visuals.py
# python3 -u -m firmware.tools.test_visuals

import time
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

def make_effects(w=W, h=H):
    return [
        ("bars", BarsEffect(w=w, h=h)),
        ("oscilloscope", OscilloscopeEffect(w=w, h=h)),
        ("radial_pulse", RadialPulseEffect(w=w, h=h)),
        ("spectral_fire", SpectralFireEffect(w=w, h=h)),
        ("vu_meter", VUMeterEffect(w=w, h=h)),
        ("wave", WaveEffect(w=w, h=h)),
    ]

def push_frame(leds: Esp32SerialDriver, frame):
    # NAJSZYBSZE i zgodne z Twoim driverem:
    # set_pixel(i, rgb) dla każdego piksela + show()
    for i, rgb in enumerate(frame):
        leds.set_pixel(i, rgb)
    leds.show()

def main():
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    import sounddevice as sd
    block = fe.nfft
    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
    stream.start()

    effects = make_effects()
    params = {
        "intensity": 0.85,
        "color_mode": "auto",
        "power": 0.55,
        "glow": 0.22,
        "mic_gain": 2.2,   # podbijaj do 3.0 jeśli nadal za cicho
    }

    i = 0
    name, eff = effects[i]
    t_switch = time.monotonic() + SWITCH_EVERY_S
    print(f"[tester] start -> {name}")

    last = time.monotonic()
    black_frames = 0

    try:
        while True:
            now = time.monotonic()
            dt = now - last
            last = now

            if now >= t_switch:
                i = (i + 1) % len(effects)
                name, eff = effects[i]
                t_switch = now + SWITCH_EVERY_S
                print(f"[tester] -> {name}")

            # audio read – czasem sounddevice potrafi rzucić wyjątek/overflow
            try:
                x, _ = stream.read(block)
                x = x[:, 0].astype(np.float32, copy=False)
            except Exception as e:
                # nie zabijaj testu – wyślij czarną klatkę i jedź dalej
                leds.clear()
                print(f"[tester] audio read error: {e}")
                time.sleep(0.05)
                continue

            features = fe.compute(x)

            try:
                frame = eff.update(features, dt, params)
            except TypeError:
                frame = eff.update(features, dt)

            # watchdog na “zgasło na zawsze”
            if not any((r or g or b) for (r, g, b) in frame):
                black_frames += 1
            else:
                black_frames = 0

            # jeśli 0 przez ~0.8s, to znaczy gate/stream padł → wymuś restart ramki
            if black_frames > int(0.8 * FPS):
                # mały “keepalive” punkt, żeby zobaczyć że pętla żyje
                frame = [(0, 0, 0)] * NUM_LEDS
                frame[0] = (10, 10, 10)
                black_frames = 0

            push_frame(leds, frame)

            sleep = DT_TARGET - (time.monotonic() - now)
            if sleep > 0:
                time.sleep(sleep)

    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        leds.clear()
        leds.close()

if __name__ == "__main__":
    main()
