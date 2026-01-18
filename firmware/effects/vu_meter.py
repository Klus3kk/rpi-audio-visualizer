import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.common import safe_bands, blank_frame

class VUMeterEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)

    def update(self, features, dt, params=None):
        try:
            bands = safe_bands(features, self.w)
            heights = (bands * (self.h - 1)).astype(int)

            frame = blank_frame(self.w, self.h)
            for x in range(self.w):
                for y in range(heights[x] + 1):
                    frame[y * self.w + x] = color_for(y/self.h, x*0.05)
            return frame
        except Exception:
            return blank_frame(self.w, self.h)
