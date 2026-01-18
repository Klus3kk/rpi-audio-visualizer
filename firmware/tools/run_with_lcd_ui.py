# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import numpy as np
import sounddevice as sd

from firmware.led.esp32_serial_driver import Esp32SerialDriver
from firmware.audio.features import FeatureExtractor

from firmware.ui.lcd_ui import LCDUI
from firmware.io.app_bridge import AppBridge

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.wave import WaveEffect


W, H = 16, 16
NUM_LEDS = W * H

ESP_PORT = "/dev/ttyUSB0"
ESP_BAUD = 115200

LED_FPS = 40.0
LED_DT = 1.0 / LED_FPS

LCD_FPS = 10.0
LCD_DT = 1.0 / LCD_FPS


def make_effects(w=W, h=H):
    return {
        "bars": BarsEffect(w=w, h=h),
        "oscilloscope": OscilloscopeEffect(w=w, h=h),
        "radial_pulse": RadialPulseEffect(w=w, h=h),
        "spectral_fire": SpectralFireEffect(w=w, h=h),
        "vu_meter": VUMeterEffect(w=w, h=h),
        "wave": WaveEffect(w=w, h=h),
    }


def apply_frame_to_esp(leds: Esp32SerialDriver, frame):
    # frame: list[(r,g,b)] length NUM_LEDS
    # Driver: set_pixel + show()
    for i, rgb in enumerate(frame):
        leds.set_pixel(i, rgb)
    leds.show()


def main():
    # --- devices ---
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=ESP_PORT, baud=ESP_BAUD, debug=False)

    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        w_panel=240, h_panel=320,
        rotate=90,     # jeśli źle: 270
        invert=True,
        dim=0.85,
    )

    app = AppBridge(rfcomm_dev="/dev/rfcomm0", tcp_host="127.0.0.1", tcp_port=8765)

    # --- audio ---
    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)
    block = fe.nfft

    stream = sd.InputStream(
        samplerate=fe.sr,
        channels=1,
        blocksize=block,
        dtype="float32",
    )
    stream.start()

    effects = make_effects()
    effect_order = list(effects.keys())
    cur_effect_name = "bars"
    cur_effect = effects[cur_effect_name]

    # --- params ---
    params = {
        "intensity": 0.65,
        "color_mode": "auto",
        "power": 0.70,   # global brightness limiter dla efektów które używają palette
        "glow": 0.20,
    }

    # mic gain (ważne dla “telefon przy głośniku”)
    mic_gain = 2.5        # zwiększ jeśli słabo reaguje
    mic_rms_scale = 10.0  # UI level z RMS

    mode = "mic"  # mic/bt

    ui.set_status("boot")
    ui.set_mode(mode)
    ui.set_level(0.0)
    ui.render()

    t_last_led = time.monotonic()
    t_last_lcd = t_last_led

    try:
        while True:
            now = time.monotonic()

            # --------- APP / BT updates (non-blocking) ----------
            ad = app.get_latest()

            # mode
            if isinstance(ad.get("mode"), str) and ad["mode"].lower() in ("mic", "bt"):
                mode = ad["mode"].lower()

            # effect override from app
            if isinstance(ad.get("effect"), str) and ad["effect"] in effects:
                cur_effect_name = ad["effect"]
                cur_effect = effects[cur_effect_name]

            # intensity override from app
            if ad.get("intensity") is not None:
                try:
                    params["intensity"] = float(ad["intensity"])
                except Exception:
                    pass

            # color_mode override from app
            if isinstance(ad.get("color_mode"), str) and ad["color_mode"]:
                params["color_mode"] = ad["color_mode"]

            # --------- AUDIO read ----------
            x, _ = stream.read(block)
            x = x[:, 0].astype(np.float32, copy=False)

            # mic gain (tylko w MIC)
            if mode == "mic":
                x = np.clip(x * mic_gain, -1.0, 1.0)

            features = fe.compute(x)

            # --------- LED update (fixed rate) ----------
            if now - t_last_led >= LED_DT:
                dt = now - t_last_led
                t_last_led = now

                # w BT możesz w przyszłości podmienić source audio na “BT stream”
                # na razie LED zawsze idzie z MIC features (ale tryb na UI się przełącza)
                try:
                    frame = cur_effect.update(features, dt, params)
                except TypeError:
                    frame = cur_effect.update(features, dt)

                if len(frame) != NUM_LEDS:
                    frame = list(frame)
                    if len(frame) != NUM_LEDS:
                        raise RuntimeError(f"{cur_effect_name}: frame len {len(frame)} != {NUM_LEDS}")

                apply_frame_to_esp(leds, frame)

            # --------- LCD update (throttled) ----------
            if now - t_last_lcd >= LCD_DT:
                t_last_lcd = now

                # level na LCD (bardziej czułe niż “surowe rms”)
                lvl = float(features.get("rms", 0.0)) * mic_rms_scale
                if lvl > 1.0:
                    lvl = 1.0

                ui.set_mode(mode)
                ui.set_level(lvl)

                # status krótkie
                st = ad.get("status") or ""
                if not st:
                    st = f"{cur_effect_name}  int={params['intensity']:.2f}"
                ui.set_status(st)

                # BT info z apki
                if mode == "bt":
                    ui.set_bt(
                        connected=bool(ad.get("connected", False)),
                        device_name=str(ad.get("device_name") or ""),
                        device_addr=str(ad.get("device_addr") or ""),
                    )
                    ui.set_track(
                        artist=str(ad.get("artist") or ""),
                        title=str(ad.get("title") or ""),
                    )
                else:
                    ui.set_bt(connected=False, device_name="", device_addr="")
                    ui.set_track(artist="", title="")

                ui.render()

            # mały sleep żeby CPU nie wyło
            time.sleep(0.001)

    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        try:
            leds.clear()
        except Exception:
            pass
        try:
            ui.close()
        except Exception:
            pass
        try:
            app.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
