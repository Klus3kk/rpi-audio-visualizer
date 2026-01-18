# firmware/tools/run_with_lcd_ui.py
# Run visualizer loop + LCD UI component.
# Start:
#   python3 -u -m firmware.tools.run_with_lcd_ui
#
# Keys:
#   m => MIC mode
#   b => BT mode (placeholder)
#   q => quit

import time
import sys
import select
import numpy as np

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

FPS = 40.0
DT_TARGET = 1.0 / FPS

SWITCH_EVERY_S = 5.0


def _stdin_key():
    # nonblocking single char (works in terminal)
    if select.select([sys.stdin], [], [], 0.0)[0]:
        return sys.stdin.read(1)
    return None


def make_effects():
    return [
        ("bars", BarsEffect(w=W, h=H)),
        ("oscilloscope", OscilloscopeEffect(w=W, h=H)),
        ("radial_pulse", RadialPulseEffect(w=W, h=H)),
        ("spectral_fire", SpectralFireEffect(w=W, h=H)),
        ("vu_meter", VUMeterEffect(w=W, h=H)),
        ("wave", WaveEffect(w=W, h=H)),
    ]


def push_frame(leds: Esp32SerialDriver, frame):
    # Your Esp32SerialDriver API: set_pixel(i,rgb) then show()
    for i, rgb in enumerate(frame):
        leds.set_pixel(i, rgb)
    leds.show()


def main():
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    ui = LCDUI({
        "width_panel": 240,
        "height_panel": 320,
        "width_ui": 320,
        "height_ui": 240,
        "rotate": 270,        # if sideways, switch 270<->90
        "spi_bus": 0,
        "spi_dev": 0,
        "spi_hz": 40_000_000,
        "dc": 25,
        "rst": 24,
        "cs": None,           # use CE0/CE1
        "invert": True,
        "madctl": 0x00,
    })

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    import sounddevice as sd
    block = fe.nfft
    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
    stream.start()

    effects = make_effects()
    idx = 0
    name, eff = effects[idx]
    t_switch = time.monotonic() + SWITCH_EVERY_S

    params = {"intensity": 0.75, "color_mode": "auto", "power": 0.70, "glow": 0.25}

    last = time.monotonic()
    fps_ema = 0.0

    ui.set_mode("mic")
    ui.set_effect(name)
    ui.set_status("RUN")

    while True:
        now = time.monotonic()
        dt = now - last
        last = now
        if dt <= 0:
            dt = DT_TARGET

        # keyboard
        k = _stdin_key()
        if k:
            k = k.lower()
            if k == "q":
                break
            if k == "m":
                ui.set_mode("mic")
                ui.set_status("MIC")
            if k == "b":
                ui.set_mode("bt")
                ui.set_status("BT")

        # switch effect (still shows UI in BT mode, but audio-driven visuals only in MIC)
        if now >= t_switch:
            idx = (idx + 1) % len(effects)
            name, eff = effects[idx]
            t_switch = now + SWITCH_EVERY_S
            ui.set_effect(name)
            ui.set_status(ui.mode.upper())

        # audio read
        x, _ = stream.read(block)
        x = x[:, 0].astype(np.float32)
        features = fe.compute(x)

        # render LEDs only in MIC mode (BT mode placeholder)
        if ui.mode == "mic":
            try:
                frame = eff.update(features, dt, params)
            except TypeError:
                frame = eff.update(features, dt)
            if len(frame) != NUM_LEDS:
                frame = list(frame)
                if len(frame) != NUM_LEDS:
                    raise RuntimeError(f"{name}: frame len {len(frame)} != {NUM_LEDS}")
            push_frame(leds, frame)
        else:
            # BT mode: keep LEDs calm (optional)
            leds.fill((0, 0, 0))
            leds.show()

        # UI stats
        energy = float(np.mean(features["bands"]))
        fps_inst = 1.0 / max(1e-6, dt)
        fps_ema = fps_inst if fps_ema <= 0 else (0.90 * fps_ema + 0.10 * fps_inst)

        ui.set_audio(rms=float(features["rms"]), energy=energy)
        ui.set_params(intensity=params["intensity"], color_mode=params["color_mode"], fps=fps_ema)
        ui.render()

        # fps limit
        sleep = DT_TARGET - (time.monotonic() - now)
        if sleep > 0:
            time.sleep(sleep)

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
