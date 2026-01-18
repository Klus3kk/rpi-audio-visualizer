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

LCD_FPS = 8.0
LCD_DT = 1.0 / LCD_FPS

SWITCH_EVERY_S = 6.0


def push_frame(driver: Esp32SerialDriver, frame):
    # driver ma show() bez argumentów -> wpisujemy do buf przez set_pixel
    # (to jest wolniejsze, ale stabilne i proste; przy 16x16 jeszcze OK)
    # Jeśli chcesz szybciej: dodaj w driverze metodę set_frame().
    for i, rgb in enumerate(frame):
        driver.set_pixel(i, rgb)
    driver.show()


def make_effects():
    return [
        ("bars", BarsEffect(w=W, h=H)),
        ("osc", OscilloscopeEffect(w=W, h=H)),
        ("radial", RadialPulseEffect(w=W, h=H)),
        ("fire", SpectralFireEffect(w=W, h=H)),
        ("vu", VUMeterEffect(w=W, h=H)),
        ("wave", WaveEffect(w=W, h=H)),
    ]


def main():
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=fe.nfft, dtype="float32")
    stream.start()

    ui = LCDUI({
        "width_panel": 240,
        "height_panel": 320,
        "spi_bus": 0,
        "spi_dev": 0,
        "spi_hz": 24_000_000,
        "dc": 25,
        "rst": 24,
        "cs": 5,          # <<< GPIO CS
        "invert": True,
        "rotate": 90,     # landscape 320x240
        "madctl_base": 0x00,
    })

    params = {
        "intensity": 0.70,
        "color_mode": "auto",
        "power": 0.75,
        "glow": 0.25,
    }

    effects = make_effects()
    idx = 0
    name, eff = effects[idx]

    t_switch = time.monotonic() + SWITCH_EVERY_S
    t_prev = time.monotonic()
    t_lcd = 0.0

    ui.set_mode("MIC")
    ui.set_effect(name)
    ui.draw({"rms": 0.0, "level": 0.0, "effect": name})

    print(f"[run] start -> {name}")

    try:
        while True:
            now = time.monotonic()
            dt = now - t_prev
            t_prev = now

            # switch effect
            if now >= t_switch:
                idx = (idx + 1) % len(effects)
                name, eff = effects[idx]
                ui.set_effect(name)
                ui.draw({"rms": 0.0, "level": 0.0, "effect": name})
                t_switch = now + SWITCH_EVERY_S
                print(f"[run] -> {name}")

            x, _ = stream.read(fe.nfft)
            x = x[:, 0].astype(np.float32, copy=False)

            features = fe.compute(x)

            # render effect
            try:
                frame = eff.update(features, dt, params)
            except TypeError:
                frame = eff.update(features, dt)

            if len(frame) != NUM_LEDS:
                frame = list(frame)
                if len(frame) != NUM_LEDS:
                    raise RuntimeError(f"{name}: frame len {len(frame)} != {NUM_LEDS}")

            push_frame(leds, frame)

            # LCD update throttled
            if (now - t_lcd) >= LCD_DT:
                t_lcd = now
                rms = float(features.get("rms", 0.0))
                # prosty poziom UI: stabilniejszy niż surowy rms
                level = min(1.0, rms * 14.0)
                ui.draw({"rms": rms, "level": level, "effect": name})

            # FPS cap
            sleep = DT_TARGET - (time.monotonic() - now)
            if sleep > 0:
                time.sleep(sleep)

    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        try:
            ui.close()
        except Exception:
            pass
        try:
            leds.clear()
            leds.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
