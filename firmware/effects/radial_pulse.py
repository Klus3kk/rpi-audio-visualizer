# firmware/effects/radial_pulse.py
import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.bars import serpentine_index

class RadialPulseEffect:
    def __init__(self, w=16, h=16, power=0.70):
        self.w = int(w); self.h = int(h)
        self.t = 0.0
        self.power = float(power)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        intensity = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        w,h = self.w, self.h
        cx, cy = (w-1)/2.0, (h-1)/2.0

        bass = float(features.get("bass", 0.0))
        mid  = float(features.get("mid", 0.0))
        tre  = float(features.get("treble", 0.0))

        # mniejsze promienie / spokojniej
        r0 = 2.0 + 5.2*bass*(0.35 + 0.75*intensity)
        thickness = 1.0 + 1.4*mid
        swirl = 0.9 + 2.2*tre

        frame = [(0,0,0)]*(w*h)
        for y in range(h):
            for x in range(w):
                dx = x - cx
                dy = y - cy
                r = (dx*dx + dy*dy) ** 0.5
                ang = np.arctan2(dy, dx)

                wave = np.sin(ang*swirl + self.t*2.6)
                dist = abs(r - (r0 + 0.9*wave))

                v = max(0.0, 1.0 - dist/max(1e-6, thickness))
                v *= (0.20 + 0.55*(0.35 + 0.75*intensity))  # dużo mniej mocy

                if v > 0.03:
                    c = color_for(v, self.t, mode=color_mode, power=self.power)
                    frame[serpentine_index(x,y,w=w,h=h,origin_bottom=True)] = c

        return frame
