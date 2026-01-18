# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import json
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

from firmware.bt.rfcomm_server import RFCOMMServer


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
    # frame: lista (r,g,b) długości NUM_LEDS
    # minimalny koszt: set_pixel + show()
    for i, (r, g, b) in enumerate(frame):
        leds.set_pixel(i, (clamp8(int(r)), clamp8(int(g)), clamp8(int(b))))
    leds.show()


def main():
    # --- LCD UI ---
    ui = LCDUI(
        dc=25, rst=24, cs_gpio=5,
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        rotate=270,
        mirror=True,              # jak lustrzane -> zmień na False
        panel_invert=False,
        dim=0.90,
        font_size=13,
        font_size_big=18,
        accent=(30, 140, 255),    # BLUE (żeby nie było pomarańczu)
        bg=(0, 0, 0),
    )

    # --- LED driver ---
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    # --- Audio + features ---
    # fmin=90 ucina rumble i uspokaja bass
    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=90, fmax=16000)

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

    params = {
        "intensity": 0.65,     # INT = intensity
        "color_mode": "auto",  # CLR = color_mode
        "power": 0.50,
        "glow": 0.25,
    }

    # ---- BT shared state ----
    bt_state = {
        "connected": False,
        "device_name": "",
        "device_addr": "",
        "artist": "",
        "title": "",
    }
    desired = {
        "mode": "mic",         # mic/bt
        "effect": effect_name,
        "intensity": params["intensity"],
        "color_mode": params["color_mode"],
    }

    def on_bt_message(msg):
        # msg = dict z apki
        # przykładowo:
        # {"mode":"bt","effect":"fire","intensity":0.55,"color_mode":"auto",
        #  "artist":"Björk","title":"Jóga","device_name":"Pixel 8","device_addr":"xx",
        #  "connected":true}
        try:
            if "mode" in msg:
                m = str(msg["mode"]).lower()
                desired["mode"] = "bt" if m == "bt" else "mic"

            if "effect" in msg:
                e = str(msg["effect"]).lower()
                if e in effects:
                    desired["effect"] = e

            if "intensity" in msg:
                v = float(msg["intensity"])
                desired["intensity"] = 0.0 if v < 0 else (1.0 if v > 1 else v)

            if "color_mode" in msg:
                cm = str(msg["color_mode"]).lower()
                if cm in ("auto", "rainbow", "mono"):
                    desired["color_mode"] = cm

            if "connected" in msg:
                bt_state["connected"] = bool(msg["connected"])
            if "device_name" in msg:
                bt_state["device_name"] = str(msg["device_name"])[:24]
            if "device_addr" in msg:
                bt_state["device_addr"] = str(msg["device_addr"])[:24]
            if "artist" in msg:
                bt_state["artist"] = str(msg["artist"])[:26]
            if "title" in msg:
                bt_state["title"] = str(msg["title"])[:26]
        except Exception:
            pass

    # start RFCOMM server (kanał 1)
    bt_srv = RFCOMMServer(channel=1, on_message=on_bt_message)
    bt_srv.start()

    # timers
    t_led = time.monotonic()
    t_lcd = time.monotonic()
    dt_led_target = 1.0 / FPS_LED
    dt_lcd_target = 1.0 / FPS_LCD

    last_feats = {"rms": 0.0, "bass": 0.0, "mid": 0.0, "treble": 0.0}

    try:
        while True:
            now = time.monotonic()

            # --- MIC audio block (odporny) ---
            try:
                x, _ = stream.read(fe.nfft)
                x = x[:, 0].astype(np.float32, copy=False)
            except Exception:
                x = np.zeros(fe.nfft, dtype=np.float32)

            # DC removal (uspokaja bass/rumble)
            x = x - float(np.mean(x))

            try:
                feats = fe.compute(x)
                last_feats = feats
            except Exception:
                feats = last_feats

            # --- Apply BT desired state (mode/effect/params) ---
            params["intensity"] = float(desired["intensity"])
            params["color_mode"] = str(desired["color_mode"])
            if desired["effect"] != effect_name:
                effect_name = desired["effect"]
                effect = effects[effect_name]

            # --- LED update ---
            if now - t_led >= dt_led_target:
                t_led = now
                try:
                    try:
                        frame = effect.update(feats, dt_led_target, params)
                    except TypeError:
                        frame = effect.update(feats, dt_led_target)
                except Exception:
                    frame = [(0, 0, 0)] * NUM_LEDS

                if len(frame) != NUM_LEDS:
                    frame = [(0, 0, 0)] * NUM_LEDS
                else:
                    # clamp + sanitize
                    frame = [(clamp8(int(r)), clamp8(int(g)), clamp8(int(b))) for (r, g, b) in frame]

                try:
                    push_frame(leds, frame)
                except Exception:
                    # chwilowe problemy serial -> ignoruj, nie zabijaj programu
                    pass

            # --- LCD update ---
            if now - t_lcd >= dt_lcd_target:
                t_lcd = now

                ui.set_mode(desired["mode"])
                ui.set_effect(effect_name)
                ui.set_visual_params(intensity=params["intensity"], color_mode=params["color_mode"])

                # MIC feats (zawsze pokazuj, nawet w BT – bo audio nadal z MIC, dopóki nie zrobimy BT audio)
                ui.set_mic_feats(
                    rms=float(feats.get("rms", 0.0)),
                    bass=float(feats.get("bass", 0.0)),
                    mid=float(feats.get("mid", 0.0)),
                    treble=float(feats.get("treble", 0.0)),
                )

                if desired["mode"] == "bt":
                    ui.set_bt(
                        connected=bt_state["connected"],
                        device_name=bt_state["device_name"],
                        device_addr=bt_state["device_addr"],
                    )
                    ui.set_track(artist=bt_state["artist"], title=bt_state["title"])
                    ui.set_status("bt mode")
                else:
                    ui.set_status("mic listening")

                try:
                    ui.render()
                except Exception:
                    # UI nie może ubijać loopa
                    pass

    finally:
        try:
            bt_srv.stop()
        except Exception:
            pass

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

        try:
            ui.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
