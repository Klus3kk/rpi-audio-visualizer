#!/usr/bin/env python3
# Run: python3 -u -m firmware.main

import asyncio
import traceback
import sys
import threading
import time
import queue
import numpy as np
import sounddevice as sd

from firmware.ui.lcd_ui import LCDUI
from firmware.audio.features import FeatureExtractor
from firmware.audio.bt_bluealsa import BlueAlsaInput
from firmware.audio.metadata import BtMetadata, bt_metadata_loop
from firmware.led.esp32_serial_driver import Esp32SerialDriver

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.plasma import PlasmaEffect
from firmware.effects.spiral import SpiralEffect
from firmware.effects.ripple import RippleEffect
from firmware.effects.kaleidoscope import KaleidoscopeEffect

from firmware.bt.ble_gatt_server import start_ble, SHARED


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


def clamp8(x: int) -> int:
    return 0 if x < 0 else (255 if x > 255 else int(x))


def f01(v, default):
    try:
        x = float(v)
    except Exception:
        x = float(default)
    return max(0.0, min(1.0, x))


def clamp_gain(v, default=1.0):
    try:
        g = float(v)
    except Exception:
        g = float(default)
    if not np.isfinite(g):
        g = float(default)
    return max(0.05, min(6.0, g))


def make_effects(w=W, h=H):
    return {
        "bars": BarsEffect(w=w, h=h),
        "osc": OscilloscopeEffect(w=w, h=h),
        "pulse": RadialPulseEffect(w=w, h=h),
        "fire": SpectralFireEffect(w=w, h=h),
        "plasma": PlasmaEffect(w=w, h=h),
        "spiral": SpiralEffect(w=w, h=h),
        "ripple": RippleEffect(w=w, h=h),
        "kaleidoscope": KaleidoscopeEffect(w=w, h=h),
    }


def safe_update_effect(effect, feats, dt, params, effect_name: str):
    try:
        try:
            frame = effect.update(feats, dt, params)
        except TypeError:
            frame = effect.update(feats, dt)
        return frame
    except Exception as e:
        log_exc(f"effect.update({effect_name})", e)
        return [(0, 0, 0)] * NUM_LEDS


def sanitize_feats(feats: dict):
    try:
        for k in ("rms", "bass", "mid", "treble"):
            v = float(feats.get(k, 0.0))
            feats[k] = 0.0 if not np.isfinite(v) else v
    except Exception:
        pass

    try:
        b = feats.get("bands", None)
        if b is not None:
            b = np.asarray(b, dtype=np.float32)
            b = np.nan_to_num(b, nan=0.0, posinf=0.0, neginf=0.0)
            feats["bands"] = np.clip(b, 0.0, 1.0)
    except Exception:
        pass
    return feats


def get_state():
    try:
        return SHARED.snapshot()
    except Exception:
        return {}


def ble_thread():
    try:
        start_ble()
    except Exception as e:
        log_exc("BLE thread", e)


class LedSender(threading.Thread):
    def __init__(self, leds: Esp32SerialDriver):
        super().__init__(daemon=True)
        self.leds = leds
        self.q: "queue.Queue[list[tuple[int,int,int]]]" = queue.Queue(maxsize=1)
        self._stop = threading.Event()

    def submit(self, frame):
        try:
            while True:
                self.q.get_nowait()
        except Exception:
            pass
        try:
            self.q.put_nowait(frame)
        except Exception:
            pass

    def run(self):
        while not self._stop.is_set():
            try:
                frame = self.q.get(timeout=0.2)
            except Exception:
                continue
            try:
                for i, (r, g, b) in enumerate(frame):
                    self.leds.set_pixel(i, (clamp8(r), clamp8(g), clamp8(b)))
                self.leds.show()
            except Exception as e:
                log_exc("LED sender", e)

    def stop(self):
        self._stop.set()


class AudioHub:
    def __init__(self, sr=SR, nfft=NFFT):
        self.sr = int(sr)
        self.nfft = int(nfft)

        self._lock = threading.Lock()
        self._mic_latest = np.zeros(self.nfft, dtype=np.float32)
        self._bt_latest = np.zeros(self.nfft, dtype=np.float32)

        self._mic: sd.InputStream | None = None
        self._bt: BlueAlsaInput | None = None
        self._bt_stop = threading.Event()
        self._bt_thread: threading.Thread | None = None

    def start_mic(self):
        def cb(indata, frames, time_info, status):
            try:
                x = indata[:, 0].astype(np.float32, copy=False)
                if x.shape[0] >= self.nfft:
                    x = x[: self.nfft]
                else:
                    pad = np.zeros(self.nfft, dtype=np.float32)
                    pad[: x.shape[0]] = x
                    x = pad
                with self._lock:
                    self._mic_latest = x.copy()
            except Exception:
                pass

        self._mic = sd.InputStream(
            samplerate=self.sr,
            channels=1,
            blocksize=self.nfft,
            dtype="float32",
            callback=cb,
        )
        self._mic.start()

    def _bt_worker(self):
        while not self._bt_stop.is_set():
            bt = self._bt
            if bt is None or not bt.is_running():
                time.sleep(0.05)
                continue
            try:
                x = bt.read_mono_f32()
                if x is None or x.shape[0] != self.nfft:
                    x = np.zeros(self.nfft, dtype=np.float32)
            except Exception:
                x = np.zeros(self.nfft, dtype=np.float32)

            with self._lock:
                self._bt_latest = x.astype(np.float32, copy=False)

            time.sleep(0.0)

    def start_bt(self, bt_addr: str | None):
        self.stop_bt()
        self._bt_latest[:] = 0.0
        self._bt = BlueAlsaInput(bt_addr=bt_addr, rate=self.sr, channels=2, chunk_frames=self.nfft)
        self._bt.start()
        self._bt_stop.clear()
        self._bt_thread = threading.Thread(target=self._bt_worker, daemon=True)
        self._bt_thread.start()

    def stop_bt(self):
        self._bt_stop.set()
        bt = self._bt
        self._bt = None
        if bt is not None:
            try:
                bt.stop()
            except Exception:
                pass
        with self._lock:
            self._bt_latest[:] = 0.0

    def get_latest(self, mode: str) -> np.ndarray:
        with self._lock:
            if mode == "bt":
                return self._bt_latest.copy()
            return self._mic_latest.copy()

    def close(self):
        self.stop_bt()
        if self._mic is not None:
            try:
                self._mic.stop()
                self._mic.close()
            except Exception:
                pass
            self._mic = None


def main():
    print("[INIT] Starting Visualizer firmware...")

    threading.Thread(target=ble_thread, daemon=True).start()

    meta = BtMetadata()
    threading.Thread(target=lambda: asyncio.run(bt_metadata_loop(meta)), daemon=True).start()

    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=270,
        mirror=True,
        panel_invert=False,
        dim=0.80,
        font_size=13,
        font_size_big=17,
        accent=(30, 140, 255),
        bg=(0, 0, 0),
    )

    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)
    led_sender = LedSender(leds)
    led_sender.start()

    fe = FeatureExtractor(samplerate=SR, nfft=NFFT, bands=16, fmin=20, fmax=20000)

    audio = AudioHub(sr=SR, nfft=NFFT)
    audio.start_mic()

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

    current_mode = "mic"

    t_led = time.monotonic()
    t_lcd = time.monotonic()
    dt_led = 1.0 / FPS_LED
    dt_lcd = 1.0 / FPS_LCD

    last_feats = {
        "rms": 0.0,
        "bands": np.zeros(16, dtype=np.float32),
        "bass": 0.0,
        "mid": 0.0,
        "treble": 0.0,
    }

    print("[RUN] Main loop started")

    try:
        while True:
            now = time.monotonic()
            st = get_state()

            raw_mode = str(st.get("mode", "mic")).lower()
            desired_mode = "bt" if (raw_mode == "bt") else "mic"

            desired_fx = str(st.get("effect", effect_name)).lower()
            if desired_fx in effects and desired_fx != effect_name:
                effect_name = desired_fx
                effect = effects[effect_name]

            params["brightness"] = f01(st.get("brightness", params["brightness"]), params["brightness"])
            params["intensity"] = f01(st.get("intensity", params["intensity"]), params["intensity"])
            params["gain"] = clamp_gain(st.get("gain", params["gain"]), params["gain"])

            try:
                sm = float(st.get("smoothing", params["smoothing"]))
                if np.isfinite(sm):
                    params["smoothing"] = max(0.0, min(0.95, sm))
            except Exception:
                pass

            if desired_mode != current_mode:
                current_mode = desired_mode
                if current_mode == "bt":
                    bt_addr = str(st.get("device_addr", "")).strip() or None
                    try:
                        audio.start_bt(bt_addr)
                    except Exception as e:
                        log_exc("audio.start_bt()", e)
                        audio.stop_bt()
                        current_mode = "mic"
                else:
                    audio.stop_bt()

            if now - t_lcd >= dt_lcd:
                t_lcd = now
                try:
                    ui.set_mode(current_mode)
                    ui.set_effect(effect_name)
                    ui.set_visual_params(intensity=params["intensity"], color_mode=params["color_mode"])
                    ui.set_mic_feats(
                        rms=float(last_feats.get("rms", 0.0)),
                        bass=float(last_feats.get("bass", 0.0)),
                        mid=float(last_feats.get("mid", 0.0)),
                        treble=float(last_feats.get("treble", 0.0)),
                    )

                    if current_mode == "bt":
                        ui.set_bt(
                            connected=bool(st.get("connected", True)),
                            device_name=str(st.get("device_name", "")),
                            device_addr=str(st.get("device_addr", "")),
                        )

                        artist = str(st.get("artist", "") or "")
                        title  = str(st.get("title", "") or "")
                        album  = str(st.get("album", "") or "")

                        if not artist and not title:
                            ms = meta.snapshot()
                            artist = ms.get("artist", "") or artist
                            title  = ms.get("title", "") or title
                            album  = ms.get("album", "") or album

                        ui.set_track(artist=artist, title=title, album=album)
                        ui.set_status(f"bt | gain={params['gain']:.2f}")
                    else:
                        ui.set_status(f"mic | gain={params['gain']:.2f}")

                    ui.render()
                except Exception as e:
                    log_exc("LCDUI.render()", e)

            x = audio.get_latest(current_mode)
            x = x - float(np.mean(x))
            x = x * float(params["gain"])

            try:
                feats = fe.compute(x, smoothing=params.get("smoothing", 0.65))
                feats = sanitize_feats(feats)
                last_feats = feats
            except Exception as e:
                log_exc("FeatureExtractor.compute()", e)

            if now - t_led >= dt_led:
                t_led = now
                frame = safe_update_effect(effect, last_feats, dt_led, params, effect_name)

                try:
                    if frame is None or len(frame) != NUM_LEDS:
                        frame = [(0, 0, 0)] * NUM_LEDS
                    else:
                        frame = [(clamp8(int(r)), clamp8(int(g)), clamp8(int(b))) for (r, g, b) in frame]
                except Exception as e:
                    log_exc("frame.sanitize", e)
                    frame = [(0, 0, 0)] * NUM_LEDS

                led_sender.submit(frame)

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[STOP] Keyboard interrupt")
    finally:
        print("[CLEANUP] Shutting down...")
        try:
            audio.close()
        except Exception:
            pass
        try:
            led_sender.stop()
        except Exception:
            pass
        try:
            leds.clear()
            leds.close()
        except Exception:
            pass
        try:
            ui.close()
        except Exception:
            pass
        print("[EXIT] Goodbye!")


if __name__ == "__main__":
    main()
