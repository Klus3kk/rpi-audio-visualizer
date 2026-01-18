# firmware/tools/run_with_lcd_ui.py
# python3 -u -m firmware.tools.run_with_lcd_ui

import time
import json
import numpy as np

from firmware.led.esp32_serial_driver import Esp32SerialDriver
from firmware.audio.features import FeatureExtractor

from firmware.effects.bars import BarsEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.wave import WaveEffect

from firmware.ui.lcd_ui import LCDUI

NOWP_PATH = "/tmp/now_playing.json"   # app/bt może tu wrzucać stan


W, H = 16, 16
NUM_LEDS = W * H

PORT = "/dev/ttyUSB0"
BAUD = 115200

FPS_LED = 40.0
DT_LED = 1.0 / FPS_LED

FPS_LCD = 10.0          # LCD wolniej, żeby nie lagowało
DT_LCD = 1.0 / FPS_LCD


def make_effects(w=W, h=H):
    return [
        ("bars", BarsEffect(w=w, h=h)),
        ("oscilloscope", OscilloscopeEffect(w=w, h=h)),
        ("radial_pulse", RadialPulseEffect(w=w, h=h)),
        ("spectral_fire", SpectralFireEffect(w=w, h=h)),
        ("vu_meter", VUMeterEffect(w=w, h=h)),
        ("wave", WaveEffect(w=w, h=h)),
    ]


def push_frame(leds: Esp32SerialDriver, frame):
    # Twój driver nie ma show(frame), tylko set_pixel() + show()
    for i, rgb in enumerate(frame):
        leds.set_pixel(i, rgb)
    leds.show()


def read_now_playing():
    # Format pliku:
    # {
    #   "mode": "bt"|"mic",
    #   "connected": true/false,
    #   "device_name": "Phone",
    #   "device_addr": "AA:BB:CC:DD:EE:FF",
    #   "artist": "Artist",
    #   "title": "Track"
    # }
    try:
        with open(NOWP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    leds = Esp32SerialDriver(num_leds=NUM_LEDS, port=PORT, baud=BAUD, debug=False)

    # LCD (Twoje działające: spidev+lgpio)
    ui = LCDUI(
        spi_bus=0, spi_dev=0, spi_hz=24_000_000,
        dc=25, rst=24, cs_gpio=5,     # jeśli CE0/CE1 -> cs_gpio=None
        rotate=90,                    # jak źle: 270
        dim=0.75,
    )

    fe = FeatureExtractor(samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000)

    import sounddevice as sd
    block = fe.nfft
    stream = sd.InputStream(samplerate=fe.sr, channels=1, blocksize=block, dtype="float32")
    stream.start()

    effects = make_effects()
    eff_i = 0
    eff_name, eff = effects[eff_i]

    params = {
        "intensity": 0.75,
        "color_mode": "auto",
        "power": 0.55,   # globalnie przyciemniaj efekty (ważne)
        "glow": 0.25,
    }

    ui.set_mode("mic")
    ui.set_status("running")
    ui.set_level(0.0)

    t_prev = time.monotonic()
    t_next_lcd = time.monotonic()
    t_next_led = time.monotonic()

    try:
        while True:
            now = time.monotonic()
            dt = now - t_prev
            t_prev = now

            # ---------- MODE + NOW PLAYING z app/BT ----------
            nowp = read_now_playing()
            if nowp:
                mode = "bt" if str(nowp.get("mode", "")).lower() == "bt" else "mic"
                ui.set_mode(mode)
                ui.set_bt(
                    connected=bool(nowp.get("connected", False)),
                    device_name=str(nowp.get("device_name", "")),
                    device_addr=str(nowp.get("device_addr", "")),
                )
                ui.set_track(
                    artist=str(nowp.get("artist", "")),
                    title=str(nowp.get("title", "")),
                )
                if mode == "bt":
                    ui.set_status("bt mode")
                else:
                    ui.set_status("mic mode")
            else:
                ui.set_mode("mic")
                ui.set_bt(connected=False, device_name="", device_addr="")
                ui.set_track(artist="", title="")
                ui.set_status("mic mode")

            # ---------- AUDIO (MIC) ----------
            # (BT audio możesz dodać później; teraz UI+matryca dalej działają)
            x, _ = stream.read(block)
            x = x[:, 0].astype(np.float32)
            features = fe.compute(x)

            # level na UI: z RMS (wzmocnione)
            lvl = min(1.0, features.get("rms", 0.0) * 12.0)
            ui.set_level(lvl)

            # ---------- LED FRAME ----------
            if now >= t_next_led:
                t_next_led = now + DT_LED

                # frame
                try:
                    frame = eff.update(features, DT_LED, params)
                except TypeError:
                    frame = eff.update(features, DT_LED)

                if len(frame) != NUM_LEDS:
                    frame = list(frame)
                    if len(frame) != NUM_LEDS:
                        continue

                push_frame(leds, frame)

            # ---------- LCD RENDER ----------
            if now >= t_next_lcd:
                t_next_lcd = now + DT_LCD
                # możesz tu też wyświetlać aktualny efekt:
                ui.render()

            # krótki sleep żeby CPU nie mieliło 100%
            time.sleep(0.001)

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
