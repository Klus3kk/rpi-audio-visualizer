import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.common import safe_bands, blank_frame

class RadialPulseEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            self.t += dt

            intensity = float((params or {}).get("intensity", 0.75))
            bands = safe_bands(features, self.w)

            bass = float(np.mean(bands[:4]))
            mid  = float(np.mean(bands[4:10]))
            tre  = float(np.mean(bands[10:]))

            cx, cy = (self.w-1)/2, (self.h-1)/2
            r0 = 2.0 + 5.0 * bass * (0.5 + intensity)

            frame = blank_frame(self.w, self.h)

            for y in range(self.h):
                for x in range(self.w):
                    dx, dy = x - cx, y - cy
                    r = (dx*dx + dy*dy) ** 0.5
                    v = max(0.0, 1.0 - abs(r - r0))
                    if v > 0.05:
                        frame[y * self.w + x] = color_for(v, self.t)

            return frame
        except Exception:
            return blank_frame(self.w, self.h)
