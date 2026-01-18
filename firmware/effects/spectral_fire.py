# firmware/effects/spectral_fire.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class SpectralFireEffect:
    def __init__(self, w=16, h=16, power=0.70):
        self.w = int(w); self.h = int(h)
        self.t = 0.0
        self.power = float(power)
        self.field = np.zeros((self.h, self.w), dtype=np.float32)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        intensity = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        w,h = self.w, self.h
        bands = features.get("bands", None)
        if bands is None:
            return [(0,0,0)]*(w*h)

        bands = np.asarray(bands, np.float32)
        xi = np.linspace(0, bands.shape[0]-1, w)
        base = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        base = np.clip(base, 0.0, 1.0)

        # mniej agresywny gain i mniej noise
        base = np.clip(base * (0.55 + 1.25*intensity), 0.0, 1.0)
        noise = (np.random.rand(w).astype(np.float32) * 0.10)

        # bottom injection (y=0 = dół w polu)
        self.field[0, :] = np.clip(0.70*self.field[0,:] + 0.90*base + noise, 0.0, 1.0)

        # propagate upward
        for y in range(1, h):
            a = self.field[y-1, :]
            left = np.roll(a, 1)
            right = np.roll(a, -1)
            v = (a + 0.55*left + 0.55*right) / (1.0 + 0.55 + 0.55)

            # chłodzenie mniejsze i bardziej stabilne
            cool = (0.015 + 0.08*(1.0-intensity)) * (1.0 + 0.70*y/h)

            self.field[y, :] = np.clip(0.88*self.field[y,:] + 0.60*v - cool, 0.0, 1.0)

        frame = [(0,0,0)]*(w*h)
        for y in range(h):
            for x in range(w):
                v = float(self.field[y,x])
                if v > 0.03:
                    # ogień mniej jasny
                    c = color_for(min(1.0, v*0.95), self.t + y*0.05, mode=color_mode, power=self.power)
                    frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = c

        return frame
