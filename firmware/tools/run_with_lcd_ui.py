# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import traceback
import sys
import threading
import time
import numpy as np
import sounddevice as sd

from firmware.ui.lcd_ui import LCDUI
from firmware.audio.features import FeatureExtractor
from firmware.audio.bt_bluealsa import BlueAlsaInput
from firmware.led.esp32_serial_driver import Esp32SerialDriver

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.wave import WaveEffect

from firmware.bt.ble_gatt_server import start_ble, SHARED


# ---------------- BLE THREAD (SAFE) ----------------
def ble_thread():
    try:
        start_ble()
    except Exception as e:
        print("[BLE] crashed:", e, file=sys.stderr)

threading.Thread(target=ble_thread, daemon=True).start()


# ---------------- CONSTANTS ----------------
W, H = 16, 16
NUM_LEDS = W * H

PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS_LED = 20.0
FPS_LCD = 20.0

SR = 44100
NFFT = 1024


# ---------------- UTILS ----------------
def log_exc(tag, e):
    print(f"[ERR] {tag}: {e}", file=sys.stderr)
    traceback.print_exc()


def clamp8(x):
    return 0 if x < 0 else (255 if x > 255 else int(x))


def push_frame(leds, frame):
    for i, (r, g, b) in enumerate(frame):
        leds.set_pixel(i, (clamp8(r), clamp8(g), clamp8(b)))
    leds.show()


def get_state():
    try:
        return SHARED.snapshot()
    except Exception:
        return {}


def f01(v, default):
    try:
        x = float(v)
    except Exception:
        x = default
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


# ---------------- EFFECTS ----------------
def make_effects(w=W, h=H):
    return {
        "bars": BarsEffect(w=w, h=h),
        "osc": OscilloscopeEffect(w=w, h=h),
        "pulse": RadialPulseEffect(w=w, h=h),
        "fire": SpectralFireEffect(w=w, h=h),
        "vu": VUMeterEffect(w=w, h=h),
        "wave": WaveEffect(w=w, h=h),
    }


def safe_update_effect(effect, feats, dt, params, name, effects):
    try:
        return effect.update(feats, dt, params), effect
    except Exception as e:
        log_exc(f"effect.update({name})", e)
        return [(0, 0, 0)] * NUM_LEDS, effects[name]


# ---------------- MAIN ----------------
def main():
    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=270, mirror=True, panel_invert=True,
        dim=0.9, font_size=13, font_size_big=18,
        accent=(30, 140, 255), bg=(0, 0, 0),
    )

    leds = Esp32SerialDriver(NUM_LEDS, PORT, BAUD, debug=False)
    fe = FeatureExtractor(samplerate=SR, nfft=NFFT, bands=16, fmin=90, fmax=16000)

    mic = sd.InputStream(
        samplerate=SR,
        channels=1,
        blocksize=NFFT,
        dtype="float32",
    )
    mic.start()

    bt_in = None

    effects = make_effects()
    effect_name = "bars"
    effect = effects[effect_name]

    params = {
        "intensity": 0.75,
        "brightness": 0.55,
        "gain": 1.0,
        "smoothing": 0.65,
        "color_mode": "auto",
    }

    current_mode = "mic"

    t_led = time.monotonic()
    t_lcd = time.monotonic()
    dt_led = 1.0 / FPS_LED
    dt_lcd = 1.0 / FPS_LCD

    last_feats = {"rms": 0.0, "bands": np.zeros(16)}

    try:
        while True:
            now = time.monotonic()
            st = get_state()

            # -------- MODE (MIC SAFE DEFAULT) --------
            desired_mode = "bt" if st.get("mode") == "bt" and st.get("connected", False) else "mic"

            if desired_mode != current_mode:
                current_mode = desired_mode
                if current_mode == "bt":
                    try:
                        bt_in = BlueAlsaInput(rate=SR, channels=2, chunk_frames=NFFT)
                        bt_in.start()
                    except Exception as e:
                        log_exc("BlueAlsaInput.start()", e)
                        bt_in = None
                        current_mode = "mic"
                else:
                    if bt_in:
                        bt_in.stop()
                        bt_in = None

            # -------- PARAMS --------
            params["intensity"] = f01(st.get("intensity", params["intensity"]), params["intensity"])
            params["brightness"] = f01(st.get("brightness", params["brightness"]), params["brightness"])

            try:
                g = float(st.get("gain", params["gain"]))
                params["gain"] = max(0.05, min(6.0, g))
            except Exception:
                params["gain"] = max(0.05, params["gain"])

            # -------- AUDIO --------
            if current_mode == "bt" and bt_in and bt_in.is_running():
                try:
                    x = bt_in.read_mono_f32()
                except Exception:
                    x = np.zeros(NFFT, np.float32)
            else:
                if mic.read_available < NFFT:
                    x = np.zeros(NFFT, np.float32)
                else:
                    x, _ = mic.read(NFFT)
                    x = x[:, 0].astype(np.float32, copy=False)

            x -= float(np.mean(x))
            x *= params["gain"]

            # -------- FEATURES --------
            try:
                feats = fe.compute(x)
                last_feats = feats
            except Exception:
                feats = last_feats

            # -------- LED --------
            if now - t_led >= dt_led:
                t_led = now
                frame, effect = safe_update_effect(effect, feats, dt_led, params, effect_name, effects)
                if frame is None or len(frame) != NUM_LEDS:
                    frame = [(0, 0, 0)] * NUM_LEDS
                push_frame(leds, frame)

            # -------- LCD --------
            if now - t_lcd >= dt_lcd:
                t_lcd = now
                ui.set_mode(current_mode)
                ui.set_effect(effect_name)
                ui.set_visual_params(intensity=params["intensity"], color_mode=params["color_mode"])
                ui.set_mic_feats(
                    rms=float(feats.get("rms", 0.0)),
                    bass=float(feats.get("bass", 0.0)),
                    mid=float(feats.get("mid", 0.0)),
                    treble=float(feats.get("treble", 0.0)),
                )
                ui.set_status("mic mode" if current_mode == "mic" else "bt mode")
                ui.render()

    finally:
        mic.stop()
        mic.close()
        if bt_in:
            bt_in.stop()
        leds.clear()
        leds.close()
        ui.close()


if __name__ == "__main__":
    main()
