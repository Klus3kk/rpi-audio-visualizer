import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

class OscilloscopeEffect:
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h
        self.t = 0.0
        self.phase = 0.0

    def update(self, features, dt, params):
        self.t += dt
        intensity = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        w,h = self.w, self.h
        rms = float(features["rms"])
        energy = float(np.mean(features["bands"]))

        # amplituda
        amp = (h/2 - 1) * min(1.0, (rms*10.0) * (0.6 + 1.2*intensity))
        self.phase += dt * (2.0 + 10.0*energy*(0.3 + intensity))

        frame = [(0,0,0)] * (w*h)
        mid = (h-1)/2

        for x in range(w):
            y = int(round(mid + amp*np.sin(self.phase + x*0.65)))
            y = max(0, min(h-1, y))
            idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)

            c = color_for(0.75, self.t + x*0.03, mode=color_mode)
            frame[idx] = c

            # glow
            if y+1 < h:
                frame[serpentine_index(x, y+1, w=w, h=h, origin_bottom=True)] = tuple(int(v*0.35) for v in c)
            if y-1 >= 0:
                frame[serpentine_index(x, y-1, w=w, h=h, origin_bottom=True)] = tuple(int(v*0.35) for v in c)

        return frame
