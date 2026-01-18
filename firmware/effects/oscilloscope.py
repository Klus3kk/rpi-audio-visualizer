import numpy as np
import colorsys

# UWAGA:
# Jeśli w bars.py masz teraz idx_serp(), to dodaj tam alias:
#   serpentine_index = idx_serp
# i wtedy ten import zadziała.
from firmware.effects.bars import serpentine_index


class OscilloscopeEffect:
    """
    Oscyloskop (linia sin) na 16x16:
    - y=0 dół, mapping serpentine_index(x,y) = kolejność fizyczna LED
    - amplituda z RMS (nie robi flasha, bo jasność ograniczona)
    - kolor zmienia się po X i delikatnie po Y (żeby nie było brzydkich bloków)
    """

    def __init__(
        self,
        w=16,
        h=16,
        v_base=0.10,      # mniej mocy
        v_top=0.25,       # mniej mocy
        s=1.0,
        power=0.85,       # globalny limiter
        glow=0.30,        # jasność sąsiadów
    ):
        self.w = int(w)
        self.h = int(h)
        self.phase = 0.0
        self.t = 0.0

        self.v_base = float(v_base)
        self.v_top = float(v_top)
        self.s = float(s)
        self.power = float(power)
        self.glow = float(glow)

        # stały gradient V po Y
        if self.h > 1:
            t = np.linspace(0.0, 1.0, self.h).astype(np.float32)
        else:
            t = np.array([0.0], dtype=np.float32)
        self._vy = np.clip(self.v_base + t * (self.v_top - self.v_base), 0.0, 1.0)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02

        intensity = float(params.get("intensity", 0.75))

        rms = float(features.get("rms", 0.0))
        bands = features.get("bands", None)
        energy = float(np.mean(bands)) if bands is not None else 0.0

        self.t += dt

        w, h = self.w, self.h
        mid = (h - 1) / 2.0

        # amplituda (z RMS), ograniczona
        amp = (h / 2.0 - 1.0) * min(1.0, (rms * 10.0) * (0.55 + 1.10 * intensity))

        # prędkość fazy (z energii)
        self.phase += dt * (2.0 + 9.0 * energy * (0.30 + intensity))

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            y = int(round(mid + amp * np.sin(self.phase + x * 0.65)))
            y = 0 if y < 0 else (h - 1 if y >= h else y)

            # kolor: hue po X + delikatne "pływanie" w czasie + lekki shift po Y
            hue = ((x / max(1, w - 1)) + 0.07 * self.t + 0.10 * (y / max(1, h - 1))) % 1.0
            v = float(self._vy[y])

            r, g, b = colorsys.hsv_to_rgb(hue, self.s, v)
            c = (int(r * 255 * self.power), int(g * 255 * self.power), int(b * 255 * self.power))

            frame[serpentine_index(x, y, w=w, h=h, origin_bottom=False)] = c

            # glow: sąsiednie piksele pionowo
            if self.glow > 0.0:
                gg = self.glow
                if y + 1 < h:
                    frame[serpentine_index(x, y + 1, w=w, h=h, origin_bottom=False)] = (
                        int(c[0] * gg), int(c[1] * gg), int(c[2] * gg)
                    )
                if y - 1 >= 0:
                    frame[serpentine_index(x, y - 1, w=w, h=h, origin_bottom=False)] = (
                        int(c[0] * gg), int(c[1] * gg), int(c[2] * gg)
                    )

        return frame
