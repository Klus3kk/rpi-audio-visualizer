# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import numpy as np
import sounddevice as sd

from firmware.led.esp32_serial_driver import Esp32SerialDriver
from firmware.audio.features import FeatureExtractor

from firmware.ui.lcd_ui import LCDUI

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

FPS = 40.0
DT_TARGET = 1.0 / FPS

SWITCH_EVERY_S = 5.0  # możesz dać 999999 jeśli nie chcesz auto-switch


def push_frame(driver: Esp32SerialDriver, frame):
    # Driver ma buf + set_pixel + show() bez argumentów
    for i, rgb in enumerate(frame):
        driver.set_pixel(i, rgb)
    driver.show()


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
    # ESP32 driver: UWAGA na kolejność argumentów w Twojej klasie
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    # LCD UI (poziomo, czarne tło, neon)
    ui = LCDUI({
        "width": 240,
        "height": 320,
        "spi_bus": 0,
        "spi_dev": 0,
        "spi_hz": 40_000_000,
        "dc": 25,
        "rst": 24,
        "rotate": 90,
        "invert": True,
        "madctl_base": 0x00,
        "ui_fps": 10.0,   # UI max 10 FPS -> nie laguje audio/LED
    })

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    block = fe.nfft
    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
    stream.start()

    effects = make_effects()
    params = {"intensity": 0.75, "color_mode": "auto", "power": 0.75, "glow": 0.25}

    idx = 0
    name, eff = effects[idx]
    t_switch = time.monotonic() + SWITCH_EVERY_S

    last = time.monotonic()
    print(f"[run] start -> {name}")

    while True:
        now = time.monotonic()
        dt = now - last
        last = now

        # auto switch
        if SWITCH_EVERY_S > 0 and now >= t_switch:
            idx = (idx + 1) % len(effects)
            name, eff = effects[idx]
            t_switch = now + SWITCH_EVERY_S
            print(f"[run] -> {name}")

        x, _ = stream.read(block)
        x = x[:, 0].astype(np.float32)
        features = fe.compute(x)

        # frame
        try:
            frame = eff.update(features, dt, params)
        except TypeError:
            frame = eff.update(features, dt)

        if len(frame) != NUM_LEDS:
            frame = list(frame)
            if len(frame) != NUM_LEDS:
                raise RuntimeError(f"{name}: frame len {len(frame)} != {NUM_LEDS}")

        push_frame(leds, frame)

        # UI update (rzadziej)
        ui.set_status(effect=name, rms=features.get("rms", 0.0), energy=float(np.mean(features.get("bands", 0.0))))
        ui.tick()

        sleep = DT_TARGET - (time.monotonic() - now)
        if sleep > 0:
            time.sleep(sleep)


if __name__ == "__main__":
    main()
