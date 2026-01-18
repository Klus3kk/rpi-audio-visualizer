import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class WaveEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.phase = 0.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            rms = safe_rms(features)
            bands = safe_bands(features, self.w)
            energy = float(np.mean(bands))

            self.phase += dt * (2.0 + 6.0 * energy)
            amp = (self.h/2 - 1) * min(1.0, rms * 12.0)
            mid = (self.h - 1)/2

            frame = blank_frame(self.w, self.h)
            for x in range(self.w):
                y = int(mid + amp * np.sin(self.phase + x*0.6))
                y = max(0, min(self.h-1, y))
                frame[y * self.w + x] = color_for(0.6, x*0.05)
            return frame
        except Exception:
            return blank_frame(self.w, self.h)
