# firmware/effects/vu_meter.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class VUMeterEffect:
    def __init__(self, w=16, h=16, power=0.70):
        self.w = int(w); self.h = int(h)
        self.power = float(power)
        self.peak = np.zeros(self.w, dtype=np.float32)
        self.level = np.zeros(self.w, dtype=np.float32)  # smoothing
        self.t = 0.0

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        intensity = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        bands = features.get("bands", None)
        if bands is None:
            return [(0,0,0)]*(self.w*self.h)

        bands = np.asarray(bands, np.float32)
        w,h = self.w, self.h

        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0]-1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands

        vals = np.clip(vals, 0.0, 1.0)

        # stabilniej: smoothing + delikatny gain
        self.level = 0.80*self.level + 0.20*vals
        vals = np.clip(self.level * (0.55 + 1.15*intensity), 0.0, 1.0)

        heights = np.round(vals * (h-1)).astype(int)

        # peak wolniej opada, ale bez “flash”
        peak_drop = dt * (0.85 + 1.35*(1.0-intensity))
        self.peak = np.maximum(self.peak - peak_drop, vals)

        frame = [(0,0,0)] * (w*h)
        for x in range(w):
            hh = int(heights[x])

            for y in range(hh+1):
                v = 0.10 + 0.60*(y/max(1,(h-1)))  # mniej jasno
                c = color_for(v, self.t + x*0.02, mode=color_mode, power=self.power)
                frame[serpentine_index(x,y,w=w,h=h,origin_bottom=True)] = c

            py = int(round(self.peak[x]*(h-1)))
            py = 0 if py < 0 else (h-1 if py >= h else py)
            # peak jako lekko jaśniejszy (nie biały)
            cpk = color_for(0.85, self.t + x*0.02, mode=color_mode, power=self.power)
            frame[serpentine_index(x,py,w=w,h=h,origin_bottom=True)] = cpk

        return frame
