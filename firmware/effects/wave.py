# firmware/effects/wave.py
import numpy as np
import colorsys
from firmware.effects.bars import serpentine_index

class WaveEffect:
    def __init__(self, w=16, h=16, power=0.70, glow=0.16):
        self.w = int(w); self.h = int(h)
        self.phase = 0.0
        self.t = 0.0
        self.power = float(power)
        self.glow = float(glow)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        intensity = float(params.get("intensity", 0.75))
        rms = float(features.get("rms", 0.0))
        bands = features.get("bands", None)
        energy = float(np.mean(bands)) if bands is not None else 0.0

        w,h = self.w, self.h
        mid = (h - 1) / 2.0

        # amplitude mniejsza i stabilniejsza
        amp = (h/2.0 - 2.0) * min(1.0, (rms * 7.0) * (0.40 + 0.85*intensity))

        # prędkość zależna od energii, ale spokojna
        self.phase += dt * (1.4 + 4.5*energy)

        frame = [(0,0,0)] * (w*h)

        for x in range(w):
            # 2 fale na raz (trochę ciekawsze)
            y = mid \
                + amp*np.sin(self.phase + x*0.55) \
                + 0.35*amp*np.sin(self.phase*0.55 + x*0.95)

            y = int(round(y))
            y = 0 if y < 0 else (h-1 if y >= h else y)

            hue = ((x / max(1,w-1)) + 0.05*self.t) % 1.0
            v = 0.05 + 0.14*(y/max(1,h-1))  # mało jasno
            r,g,b = colorsys.hsv_to_rgb(hue, 1.0, v)
            c = (int(r*255*self.power), int(g*255*self.power), int(b*255*self.power))

            frame[serpentine_index(x,y,w=w,h=h,origin_bottom=True)] = c

            if self.glow > 0.0:
                gg = self.glow
                if y+1 < h:
                    frame[serpentine_index(x,y+1,w=w,h=h,origin_bottom=True)] = (int(c[0]*gg),int(c[1]*gg),int(c[2]*gg))
                if y-1 >= 0:
                    frame[serpentine_index(x,y-1,w=w,h=h,origin_bottom=True)] = (int(c[0]*gg),int(c[1]*gg),int(c[2]*gg))

        return frame
