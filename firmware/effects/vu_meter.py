import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class VUMeterEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.level = np.zeros(self.w, dtype=np.float32)
        self.peak  = np.zeros(self.w, dtype=np.float32)
        self.t = 0.0

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
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands.astype(np.float32, copy=False)

        vals = np.clip(vals, 0.0, 1.0)
        vals = 0.25*np.roll(vals, 1) + 0.50*vals + 0.25*np.roll(vals, -1)

        gain = 0.80 + 2.40 * intensity
        vals = np.power(np.clip(vals * gain, 0.0, 1.0), 0.80)

        target = vals * (h - 1)

        att = float(np.exp(-dt / 0.05))
        rel = float(np.exp(-dt / 0.18))
        pdec = float(np.exp(-dt / 0.35))

        for x in range(w):
            t = target[x]
            cur = self.level[x]
            if t > cur:
                cur = cur * att + t * (1.0 - att)
            else:
                cur = cur * rel + t * (1.0 - rel)
            self.level[x] = cur
            self.peak[x] = max(self.peak[x] * pdec, cur)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = int(np.clip(round(self.level[x]), 0, h - 1))
            py = int(np.clip(round(self.peak[x]), 0, h - 1))

            for y in range(hh + 1):
                # V większe żeby było widać przy BRIGHTNESS=4
                v = 0.22 + 0.20 * (y / max(1, h - 1))
                c = color_for(v, self.t + 0.02*x, mode=color_mode)
                frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = (
                    int(c[0] * power), int(c[1] * power), int(c[2] * power)
                )

            # peak: jasny akcent (nie biały flash)
            vpk = 0.45
            cpk = color_for(vpk, self.t + 0.03*x, mode=color_mode)
            frame[serpentine_index(x, py, w=w, h=h, origin_bottom=True)] = (
                int(cpk[0] * power), int(cpk[1] * power), int(cpk[2] * power)
            )

        return frame
