# firmware/effects/wave.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class WaveEffect:
    """
    Wave (oscyloskop-linia) z Twoją filozofią:
    - mapping: serpentine_index(..., origin_bottom=True)
    - brak flasha: jasność limitowana (power) + kolor z palette.color_for
    - amplituda z RMS + intensity
    - prędkość z energii pasm
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.phase = 0.0
        self.t = 0.0

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        w, h = self.w, self.h
        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")
        power      = float(params.get("power", 0.85))  # global limiter
        glow       = float(params.get("glow", 0.30))   # 0..1

        rms = float(features.get("rms", 0.0))
        bands = features.get("bands", None)
        energy = float(np.mean(bands)) if bands is not None else 0.0

        # speed
        self.phase += dt * (2.0 + 8.0 * energy * (0.30 + intensity))

        # amplitude (bounded), no brightness change
        amp = (h / 2.0 - 1.0) * min(1.0, (rms * 9.0) * (0.55 + 1.10 * intensity))
        mid = (h - 1) / 2.0

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            y = int(round(mid + amp * np.sin(self.phase + x * 0.60)))
            y = 0 if y < 0 else (h - 1 if y >= h else y)

            # kolor zależny od X + czas (ładne, nie w blokach)
            v = 0.22 + 0.55 * (abs(y - mid) / max(1e-6, mid))  # stała w funkcji Y
            c = color_for(v, self.t + 0.03 * x, mode=color_mode, power=power)

            frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = c

            if glow > 0.0:
                if y + 1 < h:
                    frame[serpentine_index(x, y + 1, w=w, h=h, origin_bottom=True)] = (
                        int(c[0] * glow), int(c[1] * glow), int(c[2] * glow)
                    )
                if y - 1 >= 0:
                    frame[serpentine_index(x, y - 1, w=w, h=h, origin_bottom=True)] = (
                        int(c[0] * glow), int(c[1] * glow), int(c[2] * glow)
                    )

        return frame
