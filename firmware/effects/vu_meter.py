import numpy as np
from firmware.effects.palette import color_for

class VUMeterEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.peak = np.zeros(self.w, dtype=np.float32)
        self.t = 0.0

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        w, h = self.w, self.h
        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        bands = np.asarray(features.get("bands", np.zeros(w, np.float32)), dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands.astype(np.float32, copy=False)

        vals = np.clip(vals, 0.0, 1.0)

        # stabilność: blur po X
        vals = 0.25*np.roll(vals, 1) + 0.5*vals + 0.25*np.roll(vals, -1)

        # wzmocnienie: żeby nie było "nic"
        vals = np.clip(vals * (0.75 + 2.20 * intensity), 0.0, 1.0)

        heights = np.round(vals * (h - 1)).astype(int)

        # peak opada powoli
        decay = dt * (1.2 + 1.2 * (1.0 - intensity))
        self.peak = np.maximum(self.peak - decay, vals)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = int(heights[x])

            for y in range(hh + 1):
                # gradient po Y
                v = 0.35 + 0.55 * (y / max(1, h - 1))
                frame[y * w + x] = color_for(v, self.t + 0.02 * x, mode=color_mode)

            py = int(round(self.peak[x] * (h - 1)))
            if py < 0: py = 0
            if py >= h: py = h - 1
            frame[py * w + x] = (255, 255, 255)

        return frame
