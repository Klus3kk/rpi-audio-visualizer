import threading
import time

from firmware.effects.bars import BarsEffect
from firmware.effects.wave import WaveEffect
from firmware.effects.vu_meter import VUMeterEffect
from firmware.effects.oscilloscope import OscilloscopeEffect
from firmware.effects.radial_pulse import RadialPulseEffect
from firmware.effects.spectral_fire import SpectralFireEffect
from firmware.led.esp32_serial_driver import EspSerialDriver

def clamp8(v):
    if v < 0: return 0
    if v > 255: return 255
    return int(v)

def apply_brightness(frame, brightness):
    b = float(brightness)
    if b >= 0.999:
        return frame
    out = []
    for r, g, bl in frame:
        out.append((clamp8(r * b), clamp8(g * b), clamp8(bl * b)))
    return out

class LedEngine:
    def __init__(self, state, audio_engine, fps=50):
        self.state = state
        self.audio = audio_engine
        self.fps = int(fps)
        self._t = None
        self._leds = None
        self._effects = {
            "bars": BarsEffect(w=16, h=16),
            "wave": WaveEffect(w=16, h=16),
            "vu": VUMeterEffect(w=16, h=16),
            "scope": OscilloscopeEffect(w=16, h=16),
            "radial": RadialPulseEffect(w=16, h=16),
            "fire": SpectralFireEffect(w=16, h=16),
        }


    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def _run(self):
        self._leds = EspSerialDriver(num_leds=256, port="/dev/ttyUSB0", baud=115200, debug=True)
        last = time.perf_counter()
        try:
            while self.state.get().running:
                now = time.perf_counter()
                dt = now - last
                last = now

                d = self.state.get()
                feats = self.audio.get_features()

                fx = self._effects.get(d.effect, self._effects["bars"])
                params = {"intensity": d.intensity, "color_mode": d.color_mode}
                frame = fx.update(feats, dt, params) if fx.update.__code__.co_argcount >= 4 else fx.update(feats, dt)
                frame = apply_brightness(frame, d.brightness)


                for i, rgb in enumerate(frame):
                    self._leds.set_pixel(i, rgb)
                self._leds.show()

                time.sleep(max(0.0, (1.0 / self.fps) - (time.perf_counter() - now)))
        finally:
            try:
                self._leds.clear()
            finally:
                self._leds.close()
