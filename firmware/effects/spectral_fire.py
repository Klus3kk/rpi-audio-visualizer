# firmware/effects/spectral_fire.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))

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
        power      = float(params.get("power", 0.55))

        bands = np.asarray(features.get("bands", np.zeros(w, np.float32)), dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            base = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            base = bands.astype(np.float32, copy=False)

        base = np.clip(base, 0.0, 1.0)

        # wzmocnienie reakcji + kompresja
        gain = 0.85 + 2.60 * intensity
        base = np.power(np.clip(base * gain, 0.0, 1.0), 0.75)

        # 1) SHIFT UP (waterfall)
        self.field[1:, :] = self.field[:-1, :]

        # 2) bottom injection = aktualne pasma + drobny noise
        noise = (np.random.rand(w).astype(np.float32) * 0.06)
        self.field[0, :] = np.clip(0.92 * base + noise, 0.0, 1.0)

        # 3) lekka dyfuzja + wygaszanie w górę (żeby było “fire”)
        for y in range(1, h):
            a = self.field[y, :]
            a = (a + 0.55*np.roll(a, 1) + 0.55*np.roll(a, -1)) / (1.0 + 0.55 + 0.55)
            cool = (0.02 + 0.06*(1.0 - intensity)) * (1.0 + 0.9*(y / max(1, h-1)))
            self.field[y, :] = np.clip(a - cool, 0.0, 1.0)

        frame = [(0, 0, 0)] * (w * h)
        mode = ("auto" if color_mode == "auto" else color_mode)

        for y in range(h):
            ty = self.t + 0.04 * y
            # moc maleje z wysokością (mniej “białych” gór)
            row_power = power * (0.95 - 0.35 * (y / max(1, h-1)))
            for x in range(w):
                v = float(self.field[y, x])
                if v <= 0.01:
                    continue
                # ogień: v w palecie, ale tnie mocno globalnie
                c = color_for(_clamp01(0.06 + 0.55*v), ty + 0.02*x, mode=mode)
                frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = (
                    int(c[0] * row_power),
                    int(c[1] * row_power),
                    int(c[2] * row_power),
                )

        return frame
