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

        # "chaotyczny" mapping pasm -> kolumny (stały, ale przestawiony)
        # low->high dalej istnieje, tylko porozrzucane po X
        self.map_idx = np.array([0, 8, 1, 12, 2, 10, 3, 14, 4, 9, 5, 13, 6, 11, 7, 15], dtype=np.int32)

        # kolory naprzemiennie: zielony / pomarańczowy / czerwony
        self.hues = np.array([0.33, 0.08, 0.00] * ((self.w + 2) // 3), dtype=np.float32)[:self.w]

        # gauss po X (środek jaśniejszy)
        x = np.arange(self.w, dtype=np.float32)
        mu = (self.w - 1) / 2.0
        sigma = 0.35 * self.w
        g = np.exp(-0.5 * ((x - mu) / sigma) ** 2)
        self.gauss = (g / (g.max() + 1e-9)).astype(np.float32)

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            p = (params or {})
            intensity = float(p.get("intensity", 0.75))

            bands = safe_bands(features, self.w)
            rms = safe_rms(features)
            if rms < 0.003:
                bands[:] = 0.0

            alpha = 0.30
            bands = (1.0 - alpha) * self.prev + alpha * bands
            self.prev = bands

            bands[bands < 0.02] = 0.0
            bands = np.clip(bands * (0.6 + 1.4 * intensity), 0.0, 1.0)

            # rozrzucenie pasm po kolumnach
            bands = bands[self.map_idx]

            # gauss: środek wyżej, boki niżej (krzywa dzwonowa)
            gauss_strength = float(p.get("bars_gauss", 0.55))  # 0..1
            shape = (1.0 - gauss_strength) + gauss_strength * self.gauss
            bands = np.clip(bands * shape, 0.0, 1.0)

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
                hcol = float(self.hues[x])
                r, g, b = colorsys.hsv_to_rgb(hcol, self.hsv_s, self.hsv_v)
                R, G, B = int(r * 255), int(g * 255), int(b * 255)
                for y in range(hh + 1):
                    frame[y * self.w + x] = (R, G, B)

            return frame
        except Exception:
            return blank_frame(self.w, self.h)
