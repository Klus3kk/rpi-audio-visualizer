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

        w, h = self.w, self.h
        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")
        power      = float(params.get("power", 1.0))

        bands = np.asarray(features.get("bands", np.zeros(w, np.float32)), dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            base = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            base = bands.astype(np.float32, copy=False)

        base = np.clip(base, 0.0, 1.0)
        gain = 0.90 + 2.80 * intensity
        base = np.power(np.clip(base * gain, 0.0, 1.0), 0.78)

        # waterfall shift up
        self.field[1:, :] = self.field[:-1, :]

        # bottom injection = pasma (mniej noise, więcej sygnału)
        noise = (np.random.rand(w).astype(np.float32) * 0.03)
        self.field[0, :] = np.clip(0.98 * base + noise, 0.0, 1.0)

        # blur + cooling
        for y in range(1, h):
            a = self.field[y, :]
            a = (a + 0.60*np.roll(a, 1) + 0.60*np.roll(a, -1)) / (1.0 + 0.60 + 0.60)
            cool = (0.015 + 0.05*(1.0 - intensity)) * (1.0 + 0.9*(y / max(1, h-1)))
            self.field[y, :] = np.clip(a - cool, 0.0, 1.0)

        frame = [(0, 0, 0)] * (w * h)
        mode = ("auto" if color_mode == "auto" else color_mode)

        for y in range(h):
            ty = self.t + 0.04 * y
            for x in range(w):
                v = float(self.field[y, x])

                # V w palecie ustawiam wyżej, żeby było widać na BRIGHTNESS=4
                vv = 0.18 + 0.70 * v
                c = color_for(vv, ty + 0.02*x, mode=mode)
                frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = (
                    int(c[0] * power),
                    int(c[1] * power),
                    int(c[2] * power),
                )

        return frame
