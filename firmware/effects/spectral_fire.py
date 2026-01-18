import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.common import safe_bands, blank_frame

class SpectralFireEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.field = np.zeros((h, w), np.float32)

    def update(self, features, dt, params=None):
        try:
            bands = safe_bands(features, self.w)
            self.field[1:] = self.field[:-1]
            self.field[0] = np.clip(bands + np.random.rand(self.w)*0.02, 0, 1)

            frame = blank_frame(self.w, self.h)
            for y in range(self.h):
                for x in range(self.w):
                    frame[y * self.w + x] = color_for(self.field[y, x], y*0.05)
            return frame
        except Exception:
            return blank_frame(self.w, self.h)
