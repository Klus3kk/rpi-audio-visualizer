# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
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


W, H = 16, 16
NUM_LEDS = W * H

PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS_LED = 20.0
FPS_LCD = 30.0


def make_effects(w=W, h=H):
    # nazwy efektów będą widoczne w UI
    return {
        "bars": BarsEffect(w=w, h=h),
        "osc": OscilloscopeEffect(w=w, h=h),
        "pulse": RadialPulseEffect(w=w, h=h),
        "fire": SpectralFireEffect(w=w, h=h),
        "vu": VUMeterEffect(w=w, h=h),
        "wave": WaveEffect(w=w, h=h),
    }


def push_frame(leds: Esp32SerialDriver, frame):
    # frame: lista (r,g,b) długości NUM_LEDS
    for i, rgb in enumerate(frame):
        leds.set_pixel(i, rgb)
    leds.show()


def main():
    # --- LCD UI ---
    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=90,
        mirror=True,          # jeśli nadal “w drugą stronę” -> zmień na False
        panel_invert=False,   # czarne tło poprawnie
        dim=0.85,
        font_size=14,
        font_size_big=20,
    )

    # --- LED driver (Twoja sygnatura) ---
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    # --- Audio + features ---
    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    stream = sd.InputStream(
        samplerate=fe.sr,
        channels=1,
        blocksize=fe.nfft,
        dtype="float32",
    )
    stream.start()

    effects = make_effects()
    effect_name = "bars"
    effect = effects[effect_name]

    # visual params (pod UI i efekty)
    params = {
        "intensity": 0.75,
        "color_mode": "auto",
        "power": 0.70,
        "glow": 0.25,
    }

    ui.set_mode("mic")

    # timery
    t_led = time.monotonic()
    t_lcd = time.monotonic()
    dt_led_target = 1.0 / FPS_LED
    dt_lcd_target = 1.0 / FPS_LCD

    try:
        while True:
            now = time.monotonic()

            # --- MIC audio block ---
            x, _ = stream.read(fe.nfft)
            x = x[:, 0].astype(np.float32)
            feats = fe.compute(x)

            # --- LED update (40 FPS) ---
            if now - t_led >= dt_led_target:
                t_led = now

                # efekt -> frame
                try:
                    frame = effect.update(feats, dt_led_target, params)
                except TypeError:
                    frame = effect.update(feats, dt_led_target)

                if len(frame) != NUM_LEDS:
                    frame = list(frame)
                    if len(frame) != NUM_LEDS:
                        raise RuntimeError(f"{effect_name}: frame len {len(frame)} != {NUM_LEDS}")

                push_frame(leds, frame)

            # --- LCD update (15 FPS) ---
            if now - t_lcd >= dt_lcd_target:
                t_lcd = now

                ui.set_effect(effect_name)
                ui.set_visual_params(intensity=params["intensity"], color_mode=params["color_mode"])
                ui.set_mic_feats(
                    rms=feats.get("rms", 0.0),
                    bass=feats.get("bass", 0.0),
                    mid=feats.get("mid", 0.0),
                    treble=feats.get("treble", 0.0),
                )
                ui.set_status("mic listening")
                ui.render()

    finally:
        try:
            stream.stop()
        except Exception:
            pass
        try:
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
