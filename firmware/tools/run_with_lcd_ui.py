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


threading.Thread(target=start_ble, daemon=True).start()

W, H = 16, 16
NUM_LEDS = W * H

PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS_LED = 20.0
FPS_LCD = 20.0

SR = 44100
NFFT = 1024


def log_exc(tag: str, e: Exception):
    print(f"[ERR] {tag}: {e}", file=sys.stderr)
    traceback.print_exc()


def make_effects(w=W, h=H):
    return {
        "bars": BarsEffect(w=w, h=h),
        "osc": OscilloscopeEffect(w=w, h=h),
        "pulse": RadialPulseEffect(w=w, h=h),
        "fire": SpectralFireEffect(w=w, h=h),
        "vu": VUMeterEffect(w=w, h=h),
        "wave": WaveEffect(w=w, h=h),
    }


def clamp8(x: int) -> int:
    return 0 if x < 0 else (255 if x > 255 else x)


def push_frame(leds: Esp32SerialDriver, frame):
    for i, (r, g, b) in enumerate(frame):
        leds.set_pixel(i, (clamp8(int(r)), clamp8(int(g)), clamp8(int(b))))
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
        x = float(default)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def safe_update_effect(effect, feats, dt, params, effect_name: str, effects: dict):
    """
    Never let an effect crash the main loop.
    If effect.update throws -> log + reset effect instance + return black frame.
    """
    try:
        try:
            frame = effect.update(feats, dt, params)
        except TypeError:
            frame = effect.update(feats, dt)
        return frame, effect
    except Exception as e:
        log_exc(f"effect.update({effect_name})", e)
        # reset effect instance (best-effort)
        try:
            effect = effects[effect_name]
        except Exception:
            pass
        return [(0, 0, 0)] * NUM_LEDS, effect


def sanitize_feats(feats: dict):
    # NaN/inf guard (NaNs frequently crash visuals)
    try:
        for k, v in list(feats.items()):
            try:
                fv = float(v)
                if not np.isfinite(fv):
                    feats[k] = 0.0
            except Exception:
                feats[k] = 0.0
    except Exception:
        pass
    return feats


def main():
    # ---- LCD ----
    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=270,
        mirror=True,              # jeśli lustrzane -> False
        panel_invert=True,        # jeśli kolory złe -> False
        dim=0.90,
        font_size=13,
        font_size_big=18,
        accent=(30, 140, 255),    # BLUE
        bg=(0, 0, 0),
    )

    # ---- LED ----
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    # ---- Features ----
    fe = FeatureExtractor(samplerate=SR, nfft=NFFT, bands=16, fmin=90, fmax=16000)

    # ---- MIC ----
    mic_stream = sd.InputStream(
        samplerate=SR,
        channels=1,
        blocksize=NFFT,
        dtype="float32",
    )
    mic_stream.start()

    # ---- BT (lazy) ----
    bt_in: BlueAlsaInput | None = None

    # ---- Effects ----
    effects = make_effects()
    effect_name = "bars"
    effect = effects[effect_name]

    params = {
        "intensity": 0.75,
        "color_mode": "auto",
        "brightness": 0.55,
        "gain": 1.0,
        "smoothing": 0.65,
        "power": 0.55,
        "glow": 0.25,
    }

    current_mode = "mic"  # start always mic

    t_led = time.monotonic()
    t_lcd = time.monotonic()
    dt_led = 1.0 / FPS_LED
    dt_lcd = 1.0 / FPS_LCD

    last_feats = {"rms": 0.0, "bass": 0.0, "mid": 0.0, "treble": 0.0}

    try:
        while True:
            loop_start = time.monotonic()
            now = loop_start
            st = get_state()

            # ---- desired mode
            desired_mode = str(st.get("mode", "mic")).lower()
            desired_mode = "bt" if desired_mode == "bt" else "mic"

            # ---- effect
            desired_fx = str(st.get("effect", effect_name)).lower()
            if desired_fx in effects and desired_fx != effect_name:
                effect_name = desired_fx
                effect = effects[effect_name]

            # ---- params
            params["brightness"] = f01(st.get("brightness", params["brightness"]), params["brightness"])
            params["intensity"] = f01(st.get("intensity", params["intensity"]), params["intensity"])

            try:
                params["gain"] = float(st.get("gain", params["gain"]))
            except Exception:
                pass
            try:
                params["smoothing"] = float(st.get("smoothing", params["smoothing"]))
            except Exception:
                pass

            cm = str(st.get("color_mode", params["color_mode"])).lower()
            if cm in ("auto", "rainbow", "mono"):
                params["color_mode"] = cm

            # ---- switch mode (start/stop BT capture)
            if desired_mode != current_mode:
                current_mode = desired_mode

                if current_mode == "bt":
                    bt_addr = str(st.get("device_addr", "")).strip() or None
                    try:
                        bt_in = BlueAlsaInput(
                            bt_addr=bt_addr,
                            rate=SR,
                            channels=2,
                            chunk_frames=NFFT,
                            playback=True,
                            out_pcm="hdmi:CARD=vc4hdmi0,DEV=0",  # zmień jeśli chcesz inne wyjście
                        )
                        bt_in.start()
                    except Exception as e:
                        log_exc("BlueAlsaInput.start()", e)
                        bt_in = None
                else:
                    try:
                        if bt_in is not None:
                            bt_in.stop()
                    except Exception as e:
                        log_exc("BlueAlsaInput.stop()", e)
                    bt_in = None

            # ---- audio block
            if current_mode == "bt":
                if bt_in is not None and bt_in.is_running():
                    try:
                        x = bt_in.read_mono_f32()
                    except Exception as e:
                        log_exc("bt_in.read_mono_f32()", e)
                        x = np.zeros(NFFT, dtype=np.float32)
                else:
                    x = np.zeros(NFFT, dtype=np.float32)
            else:
                try:
                    x, _ = mic_stream.read(NFFT)
                    x = x[:, 0].astype(np.float32, copy=False)
                except Exception as e:
                    log_exc("mic_stream.read()", e)
                    x = np.zeros(NFFT, dtype=np.float32)

            # ---- stabilize low-end + gain
            try:
                x = x - float(np.mean(x))
            except Exception:
                pass
            try:
                x = x * float(params["gain"])
            except Exception:
                pass

            # ---- features
            try:
                feats = fe.compute(x)
                feats = sanitize_feats(feats)
                last_feats = feats
            except Exception as e:
                log_exc("FeatureExtractor.compute()", e)
                feats = last_feats

            # ---- LED
            if now - t_led >= dt_led:
                t_led = now

                frame, effect = safe_update_effect(effect, feats, dt_led, params, effect_name, effects)

                # frame sanity
                try:
                    if frame is None or len(frame) != NUM_LEDS:
                        frame = [(0, 0, 0)] * NUM_LEDS
                    else:
                        frame = [(clamp8(int(r)), clamp8(int(g)), clamp8(int(b))) for (r, g, b) in frame]
                except Exception as e:
                    log_exc("frame.sanitize", e)
                    frame = [(0, 0, 0)] * NUM_LEDS

                # serial safe
                try:
                    push_frame(leds, frame)
                except Exception as e:
                    log_exc("push_frame(serial)", e)
                    pass

            # ---- LCD
            if now - t_lcd >= dt_lcd:
                t_lcd = now

                try:
                    ui.set_mode(current_mode)
                    ui.set_effect(effect_name)
                    ui.set_visual_params(intensity=params["intensity"], color_mode=params["color_mode"])
                    ui.set_mic_feats(
                        rms=float(feats.get("rms", 0.0)),
                        bass=float(feats.get("bass", 0.0)),
                        mid=float(feats.get("mid", 0.0)),
                        treble=float(feats.get("treble", 0.0)),
                    )

                    if current_mode == "bt":
                        ui.set_bt(
                            connected=bool(st.get("connected", True)),
                            device_name=str(st.get("device_name", "")),
                            device_addr=str(st.get("device_addr", "")),
                        )
                        ui.set_track(
                            artist=str(st.get("artist", "")),
                            title=str(st.get("title", "")),
                        )
                        ui.set_status("bt mode")
                    else:
                        ui.set_status("mic mode")

                    ui.render()
                except Exception as e:
                    log_exc("LCDUI.render()", e)

            # ---- watchdog: slow loop != crash
            loop_dt = time.monotonic() - loop_start
            if loop_dt > 0.25:
                print(f"[WARN] slow loop: {loop_dt:.3f}s (fx={effect_name}, mode={current_mode})", file=sys.stderr)

    finally:
        try:
            if bt_in is not None:
                bt_in.stop()
        except Exception as e:
            log_exc("finally.bt_in.stop()", e)

        try:
            mic_stream.stop()
            mic_stream.close()
        except Exception as e:
            log_exc("finally.mic_stream.close()", e)

        try:
            leds.clear()
            leds.close()
        except Exception as e:
            log_exc("finally.leds.close()", e)

        try:
            ui.close()
        except Exception as e:
            log_exc("finally.ui.close()", e)


if __name__ == "__main__":
    main()
