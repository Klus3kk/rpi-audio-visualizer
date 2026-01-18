# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import numpy as np

from firmware.ui.lcd_ui import LCDUI
from firmware.audio.features import FeatureExtractor
from firmware.audio.sources import MicSource, PipeWireBtSource
from firmware.led.esp32_serial_driver import Esp32SerialDriver

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.wave import WaveEffect

from firmware.bt.ble_gatt_server import start_ble, SHARED
import threading

# BLE sterowanie (Twoja apka) - tylko control, bez audio
threading.Thread(target=start_ble, daemon=True).start()

W, H = 16, 16
NUM_LEDS = W * H

PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS_LED = 20.0
FPS_LCD = 20.0


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


def _clamp01(v: float) -> float:
    v = float(v)
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def main():
    # --- LCD UI (niebieski) ---
    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=270,
        dim=0.90,
        font_size=13,
        font_size_big=18,
    )
    # jeśli Twój LCDUI nie ma set_theme, ustaw kolor w samym lcd_ui.py na stałe (accent blue).
    # Tu zakładam, że już masz niebieski.

    # --- LED driver ---
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    # --- Audio + features ---
    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=90, fmax=16000)

    mic = MicSource(samplerate=fe.sr, blocksize=fe.nfft)
    # target opcjonalny; jak chcesz wskazać konkretny node pipewire:
    # bt = PipeWireBtSource(samplerate=fe.sr, channels=2, target="bluez_output....a2dp-sink")
    bt = PipeWireBtSource(samplerate=fe.sr, channels=2, target=None)

    effects = make_effects()
    effect_name = "bars"
    effect = effects[effect_name]

    params = {
        "intensity": 0.65,      # INT
        "color_mode": "auto",   # CLR (auto/rainbow/mono)
        "power": 0.50,
        "glow": 0.25,
    }

    # Start w MIC (tak jak chcesz)
    desired_mode = "mic"

    t_led = time.monotonic()
    t_lcd = time.monotonic()
    dt_led = 1.0 / FPS_LED
    dt_lcd = 1.0 / FPS_LCD

    last_feats = {"rms": 0.0, "bass": 0.0, "mid": 0.0, "treble": 0.0}

    try:
        while True:
            now = time.monotonic()

            # -------- 1) ZABIERZ STEROWANIE Z BLE (apka) --------
            # SHARED powinien zawierać to co apka wysyła (mode/effect/intensity/brightness/gain/smoothing + artist/title itd)
            # Zakładam, że start_ble aktualizuje SHARED["cmd"] jako dict (albo SHARED bezpośrednio).
            cmd = SHARED.get("cmd", {}) if isinstance(SHARED, dict) else {}
            if isinstance(cmd, dict):
                if "mode" in cmd:
                    m = str(cmd["mode"]).lower()
                    desired_mode = "bt" if m == "bt" else "mic"
                if "effect" in cmd:
                    e = str(cmd["effect"]).lower()
                    if e in effects:
                        effect_name = e
                        effect = effects[effect_name]
                if "intensity" in cmd:
                    params["intensity"] = _clamp01(cmd["intensity"])
                if "color_mode" in cmd:
                    cm = str(cmd["color_mode"]).lower()
                    if cm in ("auto", "rainbow", "mono"):
                        params["color_mode"] = cm

            # -------- 2) WYBIERZ ŹRÓDŁO AUDIO ZALEŻNIE OD MODE --------
            if desired_mode == "bt":
                x = bt.read(fe.nfft)   # BT audio
            else:
                x = mic.read(fe.nfft)  # MIC audio

            # bass rumble kill (uspokaja)
            x = x.astype(np.float32, copy=False)
            x = x - float(np.mean(x))

            try:
                feats = fe.compute(x)
                last_feats = feats
            except Exception:
                feats = last_feats

            # -------- 3) LED --------
            if now - t_led >= dt_led:
                t_led = now
                try:
                    try:
                        frame = effect.update(feats, dt_led, params)
                    except TypeError:
                        frame = effect.update(feats, dt_led)
                except Exception:
                    frame = [(0, 0, 0)] * NUM_LEDS

                if len(frame) != NUM_LEDS:
                    frame = [(0, 0, 0)] * NUM_LEDS
                else:
                    frame = [(clamp8(int(r)), clamp8(int(g)), clamp8(int(b))) for (r, g, b) in frame]

                try:
                    push_frame(leds, frame)
                except Exception:
                    pass

            # -------- 4) LCD --------
            if now - t_lcd >= dt_lcd:
                t_lcd = now

                ui.set_mode(desired_mode)
                ui.set_effect(effect_name)
                ui.set_visual_params(intensity=params["intensity"], color_mode=params["color_mode"])

                ui.set_mic_feats(
                    rms=float(feats.get("rms", 0.0)),
                    bass=float(feats.get("bass", 0.0)),
                    mid=float(feats.get("mid", 0.0)),
                    treble=float(feats.get("treble", 0.0)),
                )

                if desired_mode == "bt":
                    # info z apki (najprościej) – apka już ma artist/title (możesz wysyłać też device_name/addr/connected)
                    ui.set_status("bt audio")
                    if isinstance(cmd, dict):
                        ui.set_bt(
                            connected=bool(cmd.get("connected", True)),
                            device_name=str(cmd.get("device_name", ""))[:24],
                            device_addr=str(cmd.get("device_addr", ""))[:24],
                        )
                        ui.set_track(
                            artist=str(cmd.get("artist", ""))[:26],
                            title=str(cmd.get("title", ""))[:26],
                        )
                else:
                    ui.set_status("mic listening")

                try:
                    ui.render()
                except Exception:
                    pass

    finally:
        try:
            bt.close()
        except Exception:
            pass
        try:
            mic.close()
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


if __name__ == "__main__":
    main()
