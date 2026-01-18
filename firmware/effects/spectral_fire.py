# firmware/effects/spectral_fire.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class SpectralFireEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0
        self.field = np.zeros((self.h, self.w), dtype=np.float32)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")
        power      = float(params.get("power", 0.85))  # global limiter

        w, h = self.w, self.h

        bands = np.asarray(features.get("bands", np.zeros(w, dtype=np.float32)), dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            base = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            base = bands

        base = np.clip(base * (0.8 + 2.2 * intensity), 0.0, 1.0)

        # inject at bottom
        noise = (np.random.rand(w).astype(np.float32) * 0.25)
        self.field[0, :] = np.clip(0.75 * self.field[0, :] + 0.85 * base + noise, 0.0, 1.0)

        # propagate upward
        for y in range(1, h):
            a = self.field[y - 1, :]
            v = (a + 0.65 * np.roll(a, 1) + 0.65 * np.roll(a, -1)) / (1.0 + 0.65 + 0.65)

            cool = (0.02 + 0.12 * (1.0 - intensity)) * (1.0 + 0.8 * (y / h))
            self.field[y, :] = np.clip(0.92 * self.field[y, :] + 0.55 * v - cool, 0.0, 1.0)

        frame = [(0, 0, 0)] * (w * h)

        # "auto" -> ogniste auto (time shift), reszta bez zmian
        mode = ("auto" if color_mode == "auto" else color_mode)

        for y in range(h):
            ty = self.t + y * 0.03
            for x in range(w):
                v = float(self.field[y, x])
                if v <= 0.01:
                    continue
                frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = color_for(
                    min(1.0, v * 1.15), ty, mode=mode, power=power
                )

        return frame
