# firmware/effects/vu_meter.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))

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
        power      = float(params.get("power", 0.55))

        bands = np.asarray(features.get("bands", np.zeros(w, np.float32)), dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands.astype(np.float32, copy=False)

        vals = np.clip(vals, 0.0, 1.0)

        # lekkie wygładzenie przestrzenne
        vals = 0.25*np.roll(vals, 1) + 0.50*vals + 0.25*np.roll(vals, -1)

        # wzmocnienie wizualne + delikatna kompresja
        gain = 0.65 + 2.10 * intensity
        vals = np.power(np.clip(vals * gain, 0.0, 1.0), 0.78)

        # envelope (attack/release)
        att = float(np.exp(-dt / 0.06))
        rel = float(np.exp(-dt / 0.22))

        # peak hold opada wolniej
        pdec = float(np.exp(-dt / 0.45))

        for x in range(w):
            t = vals[x] * (h - 1)
            cur = self.level[x]
            if t > cur:
                cur = cur * att + t * (1.0 - att)
            else:
                cur = cur * rel + t * (1.0 - rel)
            self.level[x] = cur

            self.peak[x] = max(self.peak[x] * pdec, cur)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = int(round(_clamp01(self.level[x] / max(1.0, (h - 1))) * (h - 1)))
            py = int(round(_clamp01(self.peak[x]  / max(1.0, (h - 1))) * (h - 1)))

            # fill
            for y in range(hh + 1):
                # v zależne od y (ładny gradient, mała moc)
                v = 0.08 + 0.18 * (y / max(1, h - 1))
                c = color_for(v, self.t + 0.02*x, mode=color_mode)
                c = (int(c[0] * power), int(c[1] * power), int(c[2] * power))
                frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = c

            # peak (nie biały flash, tylko jaśniejszy akcent)
            if 0 <= py < h:
                vpk = 0.22
                cpk = color_for(vpk, self.t + 0.03*x, mode=color_mode)
                cpk = (int(cpk[0] * power), int(cpk[1] * power), int(cpk[2] * power))
                frame[serpentine_index(x, py, w=w, h=h, origin_bottom=True)] = cpk

        return frame
