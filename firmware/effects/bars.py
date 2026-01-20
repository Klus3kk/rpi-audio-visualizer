import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class BarsEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)

        self.level = np.zeros(self.w, np.float32)
        self.peak  = np.zeros(self.w, np.float32)
        self.prev  = np.zeros(self.w, np.float32)

        self.attack = 0.6
        self.decay = 6.0
        self.peak_decay = 3.0

        self.hsv_s = 1.0
        self.hsv_v = 0.22

        # Pasma: 1250Hz do 20kHz (liniowo)
        # Każde pasmo ~1172 Hz (18750/16)
        # Kolory: od zielonego (1250Hz) przez żółty/pomarańczowy do czerwonego (20kHz)
        # HSV: hue od 0.33 (zielony) do 0.0 (czerwony)
        self.base_hue = np.linspace(0.33, 0.0, self.w, dtype=np.float32)

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            intensity = float((params or {}).get("intensity", 0.75))

            bands = safe_bands(features, self.w)
            rms = safe_rms(features)

            if rms < 0.003:
                bands[:] = 0.0

            alpha = 0.30
            bands = (1.0 - alpha) * self.prev + alpha * bands
            self.prev = bands

            bands[bands < 0.02] = 0.0
            bands = np.clip(bands * (0.6 + 1.4 * intensity), 0.0, 1.0)

            target = bands * (self.h - 1)

            fall = self.decay * dt
            pfall = self.peak_decay * dt

            for x in range(self.w):
                if target[x] > self.level[x]:
                    self.level[x] = (1 - self.attack) * self.level[x] + self.attack * target[x]
                else:
                    self.level[x] = max(0.0, self.level[x] - fall)

                if self.level[x] > self.peak[x]:
                    self.peak[x] = self.level[x]
                else:
                    self.peak[x] = max(0.0, self.peak[x] - pfall)

            frame = blank_frame(self.w, self.h)

            for x in range(self.w):
                hh = int(self.level[x])
                for y in range(hh + 1):
                    hcol = self.base_hue[x]
                    r,g,b = colorsys.hsv_to_rgb(hcol, self.hsv_s, self.hsv_v)
                    frame[y * self.w + x] = (int(r*255), int(g*255), int(b*255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)