import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class VUMeterEffect:
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h
        self.peak = np.zeros(w, dtype=np.float32)
        self.t = 0.0

    def update(self, features, dt, params):
        self.t += dt
        intensity = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        bands = features["bands"]
        w, h = self.w, self.h

        vals = bands
        if vals.shape[0] != w:
            xi = np.linspace(0, vals.shape[0]-1, w)
            vals = np.interp(xi, np.arange(vals.shape[0]), vals)

        # intensywność = wzmocnienie wizualne
        vals = np.clip(vals * (0.6 + 1.8*intensity), 0.0, 1.0)
        heights = np.round(vals * (h-1)).astype(int)

        decay = dt * (0.6 + 1.6*(1.0-intensity))
        self.peak = np.maximum(self.peak - decay, vals)

        frame = [(0,0,0)] * (w*h)
        for x in range(w):
            hh = heights[x]
            for y in range(hh+1):
                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                v = (y / max(1,(h-1))) * 0.9 + 0.1
                frame[idx] = color_for(v, self.t, mode=color_mode)

            py = int(round(self.peak[x]*(h-1)))
            pidx = serpentine_index(x, py, w=w, h=h, origin_bottom=True)
            frame[pidx] = (255,255,255)

        return frame
