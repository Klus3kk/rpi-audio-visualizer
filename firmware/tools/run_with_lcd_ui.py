# firmware/tools/test_visuals_with_ui.py
# Run:
#   python3 -u -m firmware.tools.test_visuals_with_ui
#
# Integrates LCDUI component + your ESP32 serial driver + mic features.
# Bluetooth mode is UI-only here: it queries system bluetooth status and shows it.
# (Audio source switching is handled in your main runner later.)

import time
import subprocess
import numpy as np

from firmware.led.esp32_serial_driver import Esp32SerialDriver
from firmware.audio.features import FeatureExtractor

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.wave import WaveEffect

from firmware.ui.lcd_ui import LCDUI, UIState, BTStatus

W, H = 16, 16
NUM_LEDS = W * H
PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS = 40.0
DT_TARGET = 1.0 / FPS

EFFECTS = [
    ("bars", BarsEffect(w=W, h=H)),
    ("oscilloscope", OscilloscopeEffect(w=W, h=H)),
    ("radial_pulse", RadialPulseEffect(w=W, h=H)),
    ("spectral_fire", SpectralFireEffect(w=W, h=H)),
    ("vu_meter", VUMeterEffect(w=W, h=H)),
    ("wave", WaveEffect(w=W, h=H)),
]
COLOR_MODES = ["auto", "rainbow", "mono"]


def bt_snapshot() -> BTStatus:
    """
    Minimal non-invasive BT status from bluetoothctl.
    Works if bluetoothctl exists and controller is up.
    """
    st = BTStatus()
    try:
        out = subprocess.check_output(["bluetoothctl", "show"], text=True, timeout=0.4)
        st.enabled = ("Powered: yes" in out)
        st.advertising = ("Discoverable: yes" in out) or ("Pairable: yes" in out)
    except Exception:
        return st

    # best-effort: connected device name/address
    try:
        info = subprocess.check_output(["bluetoothctl", "info"], text=True, timeout=0.4)
        # bluetoothctl info without addr often prints "Missing device address" => ignore
        if "Device" in info and "Connected: yes" in info:
            st.connected = True
    except Exception:
        pass

    return st


def main():
    ui = LCDUI({
        "backend": "luma",
        "driver": "st7789",
        "spi_port": 0,
        "spi_device": 0,
        "gpio_dc": 24,
        "gpio_rst": 25,
        "gpio_cs": None,
        "rotate": 0,
        "width": 240,
        "height": 240,
        "spi_hz": 32000000,
        "gpio_buttons": False,
    })

    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)
    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    import sounddevice as sd
    block = fe.nfft
    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
    stream.start()

    effect_names = [n for n, _ in EFFECTS]
    cur_idx = 0
    cur_name, cur_eff = EFFECTS[cur_idx]
    ui.set_effects(effect_names, cur_name)

    params = {"intensity": 0.75, "color_mode": "auto"}
    state = UIState(mode="MIC", effect_name=cur_name, intensity=params["intensity"], color_mode=params["color_mode"])

    t_prev = time.monotonic()
    fps_ema = 0.0
    fps_a = 0.90
    t_bt = 0.0

    try:
        while True:
            now = time.monotonic()
            dt = now - t_prev
            t_prev = now
            if dt <= 0:
                dt = DT_TARGET

            # UI inputs
            actions = ui.poll_inputs()
            if actions.get("quit"):
                break

            if actions.get("toggle_mode"):
                state.mode = "BT" if state.mode == "MIC" else "MIC"

            if "effect" in actions:
                cur_name = actions["effect"]
                cur_idx = effect_names.index(cur_name)
                cur_eff = EFFECTS[cur_idx][1]

            if "intensity_step" in actions:
                params["intensity"] = float(np.clip(params["intensity"] + actions["intensity_step"], 0.05, 1.0))

            if actions.get("cycle_color"):
                i = COLOR_MODES.index(params["color_mode"])
                params["color_mode"] = COLOR_MODES[(i + 1) % len(COLOR_MODES)]

            # features (MIC always computed; BT mode may still show visuals from MIC unless you switch audio source)
            x, _ = stream.read(block)
            x = x[:, 0].astype(np.float32)
            features = fe.compute(x)

            # visuals
            try:
                frame = cur_eff.update(features, dt, params)
            except TypeError:
                frame = cur_eff.update(features, dt)

            for i, rgb in enumerate(frame):
                leds.set_pixel(i, rgb)
            leds.show()

            # state update
            fps = 1.0 / dt
            fps_ema = fps_a * fps_ema + (1.0 - fps_a) * fps

            state.effect_name = cur_name
            state.intensity = params["intensity"]
            state.color_mode = params["color_mode"]
            state.fps = fps_ema
            state.serial_ok = True
            state.last_err = ""

            # MIC metrics
            state.rms = float(features.get("rms", 0.0))
            state.bass = float(features.get("bass", 0.0))
            state.mid = float(features.get("mid", 0.0))
            state.treble = float(features.get("treble", 0.0))
            b = features.get("bands", None)
            state.bands = list(b) if b is not None else None

            # BT snapshot (rate-limited)
            if state.mode == "BT" and (now - t_bt) > 0.5:
                state.bt = bt_snapshot()
                t_bt = now

            ui.render(state)

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
            leds.clear()
            leds.close()
        except Exception:
            pass
        ui.close()


if __name__ == "__main__":
    main()
