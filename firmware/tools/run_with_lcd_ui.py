# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import threading
import numpy as np
import sounddevice as sd

from firmware.ui.lcd_ui import LCDUI
from firmware.audio.features import FeatureExtractor
from firmware.led.esp32_serial_driver import Esp32SerialDriver

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.wave import WaveEffect

# BLE GATT – JEDYNA komunikacja z apką
from firmware.bt.ble_gatt_server import start_ble, SHARED

# ===================== CONFIG =====================

W, H = 16, 16
NUM_LEDS = W * H

PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS_LED = 20.0
FPS_LCD = 20.0

# ===================== EFFECTS =====================

def make_effects(w=W, h=H):
    return {
        "bars": BarsEffect(w=w, h=h),
        "osc": OscilloscopeEffect(w=w, h=h),
        "pulse": RadialPulseEffect(w=w, h=h),
        "fire": SpectralFireEffect(w=w, h=h),
        "vu": VUMeterEffect(w=w, h=h),
        "wave": WaveEffect(w=w, h=h),
    }

def clamp8(x):
    return 0 if x < 0 else (255 if x > 255 else x)

def push_frame(leds, frame):
    for i, (r, g, b) in enumerate(frame):
        leds.set_pixel(i, (clamp8(int(r)), clamp8(int(g)), clamp8(int(b))))
    leds.show()

# ===================== MAIN =====================

def main():
    # ---- BLE ----
    threading.Thread(target=start_ble, daemon=True).start()

    # ---- LCD ----
    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=270,
        mirror=False,
        panel_invert=False,
        dim=0.90,
        font_size=13,
        font_size_big=18,
        # accent=(30, 140, 255),
        # bg=(0, 0, 0),
    )

    # ---- LED ----
    leds = Esp32SerialDriver(
        num_leds=NUM_LEDS,
        port=PORT,
        baud=BAUD,
        debug=False,
    )

    # ---- AUDIO ----
    fe = FeatureExtractor(
        samplerate=44100,
        nfft=1024,
        bands=16,
        fmin=90,       # uspokaja bass
        fmax=16000,
    )

    stream = sd.InputStream(
        samplerate=fe.sr,
        channels=1,
        blocksize=fe.nfft,
        dtype="float32",
    )
    stream.start()

    # ---- EFFECTS ----
    effects = make_effects()
    effect_name = "bars"
    effect = effects[effect_name]

    params = {
        "intensity": 0.65,
        "color_mode": "auto",
        "gain": 1.0,
        "smoothing": 0.65,
    }

    # ---- TIMERS ----
    t_led = time.monotonic()
    t_lcd = time.monotonic()

    dt_led = 1.0 / FPS_LED
    dt_lcd = 1.0 / FPS_LCD

    last_feats = {"rms": 0, "bass": 0, "mid": 0, "treble": 0}

    try:
        while True:
            now = time.monotonic()

            # ===== AUDIO =====
            try:
                x, _ = stream.read(fe.nfft)
                x = x[:, 0].astype(np.float32, copy=False)
                x -= np.mean(x)  # DC removal
                feats = fe.compute(x)
                last_feats = feats
            except Exception:
                feats = last_feats

            # ===== BLE STATE =====
            state = SHARED.snapshot()

            mode = state.get("mode", "mic")
            new_effect = state.get("effect", effect_name)

            if new_effect != effect_name and new_effect in effects:
                effect_name = new_effect
                effect = effects[effect_name]

            params["intensity"] = float(state.get("intensity", params["intensity"]))
            params["color_mode"] = state.get("color_mode", params["color_mode"])
            params["gain"] = float(state.get("gain", params["gain"]))
            params["smoothing"] = float(state.get("smoothing", params["smoothing"]))

            # ===== LED =====
            if now - t_led >= dt_led:
                t_led = now
                try:
                    frame = effect.update(feats, dt_led, params)
                    if len(frame) != NUM_LEDS:
                        raise ValueError
                except Exception:
                    frame = [(0, 0, 0)] * NUM_LEDS

                try:
                    push_frame(leds, frame)
                except Exception:
                    pass

            # ===== LCD =====
            if now - t_lcd >= dt_lcd:
                t_lcd = now
                try:
                    ui.set_mode(mode)
                    ui.set_effect(effect_name)
                    ui.set_visual_params(
                        intensity=params["intensity"],
                        color_mode=params["color_mode"],
                    )
                    ui.set_mic_feats(
                        rms=feats["rms"],
                        bass=feats["bass"],
                        mid=feats["mid"],
                        treble=feats["treble"],
                    )
                    ui.set_status("bt mode" if mode == "bt" else "mic listening")
                    ui.render()
                except Exception:
                    pass

    finally:
        stream.stop()
        stream.close()
        leds.clear()
        leds.close()
        ui.close()

# ===================== ENTRY =====================

if __name__ == "__main__":
    main()
