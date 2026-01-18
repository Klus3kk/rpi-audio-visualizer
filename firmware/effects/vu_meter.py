# firmware/effects/vu_meter.py
import numpy as np
from firmware.effects.bars import serpentine_index
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

        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")
        power      = float(params.get("power", 0.85))  # global limiter

        w, h = self.w, self.h

        bands = np.asarray(features.get("bands", np.zeros(w, dtype=np.float32)), dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands

        # visual gain
        vals = np.clip(vals * (0.6 + 1.8 * intensity), 0.0, 1.0)
        heights = np.round(vals * (h - 1)).astype(int)

        # peak hold (slower fall)
        decay = dt * (0.6 + 1.6 * (1.0 - intensity))
        self.peak = np.maximum(self.peak - decay, vals)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = int(heights[x])

            # full fill
            for y in range(hh + 1):
                v = (y / max(1, (h - 1))) * 0.9 + 0.1
                frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = color_for(
                    v, self.t + 0.02 * x, mode=color_mode, power=power
                )

            # peak pixel
            py = int(round(float(self.peak[x]) * (h - 1)))
            if 0 <= py < h:
                frame[serpentine_index(x, py, w=w, h=h, origin_bottom=True)] = (255, 255, 255)

        return frame
