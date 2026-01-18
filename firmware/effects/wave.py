import numpy as np
from firmware.effects.palette import color_for

class WaveEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.phase = 0.0
        self.t = 0.0

        # smoothing żeby nie znikało
        self._amp = 0.0

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        w, h = self.w, self.h
        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        rms = float(features.get("rms", 0.0))
        bands = features.get("bands", None)
        energy = float(np.mean(bands)) if bands is not None else 0.0

        # amplituda: RMS + energy (zawsze coś widać)
        raw = (rms * 18.0) * (0.65 + 1.10 * intensity) + 0.65 * energy
        raw = 0.15 + 0.85 * max(0.0, min(1.0, raw))  # MIN=0.15

        a = float(np.exp(-dt / 0.10))
        self._amp = self._amp * a + raw * (1.0 - a)

        amp = (h / 2.0 - 1.0) * self._amp
        mid = (h - 1) / 2.0

        # speed
        self.phase += dt * (1.6 + 7.0 * energy * (0.25 + intensity))

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            y = int(round(mid + amp * np.sin(self.phase + x * 0.60)))
            if y < 0: y = 0
            if y >= h: y = h - 1

            # kolor stabilny, bez zależności od głośności
            v = 0.55
            c = color_for(v, self.t + 0.03 * x, mode=color_mode)

            frame[y * w + x] = c

            # glow pionowy (też row-major)
            if y + 1 < h:
                frame[(y + 1) * w + x] = (int(c[0] * 0.30), int(c[1] * 0.30), int(c[2] * 0.30))
            if y - 1 >= 0:
                frame[(y - 1) * w + x] = (int(c[0] * 0.30), int(c[1] * 0.30), int(c[2] * 0.30))

        return frame
