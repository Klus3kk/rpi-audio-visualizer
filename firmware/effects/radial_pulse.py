import numpy as np
from firmware.effects.palette import color_for

class RadialPulseEffect:
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h
        self.t = 0.0

    def _idx(self, x, y):
        # zwykły index (tu łatwiej liczyć 2D), mapowanie na serpentine robimy na końcu
        return y*self.w + x

    def update(self, features, dt, params):
        self.t += dt
        intensity = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        w,h = self.w, self.h
        cx, cy = (w-1)/2, (h-1)/2

        bass = float(features["bass"])
        mid = float(features["mid"])
        treble = float(features["treble"])

        # promień i grubość zależne od energii
        r0 = (2.0 + 6.5*bass*(0.5+intensity))
        thickness = 0.9 + 1.8*mid
        swirl = 1.2 + 2.8*treble

        frame2d = [(0,0,0)]*(w*h)
        for y in range(h):
            for x in range(w):
                dx = x - cx
                dy = y - cy
                r = (dx*dx + dy*dy) ** 0.5
                ang = np.arctan2(dy, dx)

                wave = np.sin(ang*swirl + self.t*3.2)
                dist = abs(r - (r0 + 1.2*wave))
                v = max(0.0, 1.0 - dist/thickness)

                v *= (0.35 + 0.65*(0.4 + intensity))  # ogólna moc
                if v > 0.02:
                    frame2d[self._idx(x,y)] = color_for(v, self.t, mode=color_mode)

        # teraz mapowanie 2D→serpentine index
        # użyjemy tej samej funkcji co bars
        from firmware.effects.bars import serpentine_index
        frame = [(0,0,0)]*(w*h)
        for y in range(h):
            for x in range(w):
                src = frame2d[self._idx(x,y)]
                dst = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                frame[dst] = src

        return frame
