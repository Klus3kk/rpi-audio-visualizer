import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class OscilloscopeEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.phase = 0.0
        self.t = 0.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            self.t += dt

            rms = safe_rms(features)
            bands = safe_bands(features, self.w)
            energy = float(np.mean(bands))

            intensity = float((params or {}).get("intensity", 0.75))

            amp = (self.h/2 - 1) * min(1.0, rms * 10.0) * (0.5 + intensity)
            mid = (self.h - 1) / 2.0

            self.phase += dt * (2.0 + 8.0 * energy)

            frame = blank_frame(self.w, self.h)

            for x in range(self.w):
                y = int(mid + amp * np.sin(self.phase + x * 0.6))
                y = max(0, min(self.h - 1, y))

                hue = (x / max(1, self.w - 1) + 0.05 * self.t) % 1.0
                r,g,b = colorsys.hsv_to_rgb(hue, 1.0, 0.25)
                frame[y * self.w + x] = (int(r*255), int(g*255), int(b*255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)
