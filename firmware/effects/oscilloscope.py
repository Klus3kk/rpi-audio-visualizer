# firmware/effects/oscilloscope.py
import numpy as np
import colorsys
from firmware.effects.bars import serpentine_index

class OscilloscopeEffect:
    def __init__(self, w=16, h=16, power=0.70, glow=0.18):
        self.w = int(w); self.h = int(h)
        self.phase = 0.0
        self.t = 0.0
        self.power = float(power)
        self.glow = float(glow)

        t = np.linspace(0.0, 1.0, self.h).astype(np.float32) if self.h > 1 else np.array([0.0], np.float32)
        self._vy = np.clip(0.05 + t * (0.16 - 0.05), 0.0, 1.0)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        intensity = float(params.get("intensity", 0.75))

        rms = float(features.get("rms", 0.0))
        bands = features.get("bands", None)
        energy = float(np.mean(bands)) if bands is not None else 0.0

        self.t += dt

        w,h = self.w, self.h
        mid = (h - 1) / 2.0

        # mniejsza amplituda i limit (żeby nie waliło po całej macierzy)
        amp = (h / 2.0 - 2.0) * min(1.0, (rms * 7.5) * (0.45 + 0.85*intensity))

        # wolniejsza faza
        self.phase += dt * (1.6 + 5.0 * energy * (0.25 + 0.75*intensity))

        frame = [(0,0,0)] * (w*h)

        for x in range(w):
            y = int(round(mid + amp * np.sin(self.phase + x * 0.62)))
            y = 0 if y < 0 else (h-1 if y >= h else y)

            hue = ((x / max(1,w-1)) + 0.04*self.t + 0.10*(y/max(1,h-1))) % 1.0
            v = float(self._vy[y])

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
