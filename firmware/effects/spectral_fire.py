import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class SpectralFireEffect:
    def __init__(self, w=16, h=16):
        self.w=w; self.h=h
        self.t=0.0
        self.field = np.zeros((h,w), dtype=np.float32)

    def update(self, features, dt, params):
        self.t += dt
        intensity = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        w,h = self.w, self.h
        bands = features["bands"]
        xi = np.linspace(0, bands.shape[0]-1, w)
        base = np.interp(xi, np.arange(bands.shape[0]), bands)
        base = np.clip(base * (0.8 + 2.2*intensity), 0.0, 1.0)

        # inject energy at bottom row
        noise = (np.random.rand(w).astype(np.float32) * 0.25)
        self.field[0,:] = np.clip(0.75*self.field[0,:] + 0.85*base + noise, 0.0, 1.0)

        # propagate upward with cooling and blur
        for y in range(1, h):
            a = self.field[y-1,:]
            left = np.roll(a, 1)
            right = np.roll(a, -1)
            v = (a + 0.65*left + 0.65*right) / (1.0 + 0.65 + 0.65)
            cool = (0.02 + 0.12*(1.0-intensity)) * (1.0 + 0.8*y/h)
            self.field[y,:] = np.clip(0.92*self.field[y,:] + 0.55*v - cool, 0.0, 1.0)

        frame = [(0,0,0)]*(w*h)
        for y in range(h):
            for x in range(w):
                v = self.field[y,x]
                if v > 0.01:
                    # ogień: kolor_mode auto/rainbow/mono, ale “auto” daje ogień z time shift
                    c = color_for(min(1.0, v*1.15), self.t + y*0.03, mode=("auto" if color_mode=="auto" else color_mode))
                    frame[serpentine_index(x,y,w=w,h=h,origin_bottom=True)] = c
        return frame
