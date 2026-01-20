import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.common import safe_bands, blank_frame

class VUMeterEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)

    def update(self, features, dt, params=None):
        try:
            # Pasma: 1250Hz do 20kHz (liniowo)
            bands = safe_bands(features, self.w)
            heights = (bands * (self.h - 1)).astype(int)

            frame = blank_frame(self.w, self.h)
            
            for x in range(self.w):
                # Każde pasmo to ~1172 Hz
                # Kolory: gradient od zielonego (niskie freq) do czerwonego (wysokie freq)
                for y in range(heights[x] + 1):
                    # Kolor zależy od pasma (x) - gradient 1.25kHz -> 20kHz
                    # hue: 0.33 (zielony) -> 0.0 (czerwony)
                    hue = 0.33 - (x / max(1, self.w - 1)) * 0.33
                    frame[y * self.w + x] = color_for(y/self.h, hue, mode="auto")
            return frame
        except Exception:
            return blank_frame(self.w, self.h)