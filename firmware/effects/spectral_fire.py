import numpy as np
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

        w, h = self.w, self.h
        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        bands = np.asarray(features.get("bands", np.zeros(w, np.float32)), dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            base = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            base = bands.astype(np.float32, copy=False)

        base = np.clip(base, 0.0, 1.0)

        # mocniejsza reakcja
        base = np.power(np.clip(base * (0.90 + 2.80 * intensity), 0.0, 1.0), 0.65)

        # shift up (ogień idzie w górę)
        self.field[1:, :] = self.field[:-1, :]

        # dół = sygnał + odrobina szumu (mało)
        noise = (np.random.rand(w).astype(np.float32) * 0.02)
        self.field[0, :] = np.clip(0.92 * base + noise, 0.0, 1.0)

        # rozmycie + chłodzenie
        for y in range(1, h):
            a = self.field[y, :]
            a = (a + 0.70*np.roll(a, 1) + 0.70*np.roll(a, -1)) / (1.0 + 0.70 + 0.70)

            cool = (0.020 + 0.060 * (1.0 - intensity)) * (1.0 + 0.8 * (y / max(1, h-1)))
            self.field[y, :] = np.clip(a - cool, 0.0, 1.0)

        frame = [(0, 0, 0)] * (w * h)

        for y in range(h):
            for x in range(w):
                v = float(self.field[y, x])

                # zawsze coś: v -> 0.18..1.0
                vv = 0.18 + 0.82 * v
                frame[y * w + x] = color_for(vv, self.t + 0.03 * y + 0.01 * x, mode=color_mode)

        return frame
