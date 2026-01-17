import numpy as np
import colorsys

def serpentine_index(x, y, w=16, h=16, origin_bottom=True):
    if origin_bottom:
        y = (h - 1) - y
    if y % 2 == 0:
        return y * w + x
    return y * w + (w - 1 - x)

class BarsEffect:
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h
        self.level = np.zeros(w, dtype=np.float32)  # poziom w pikselach 0..h-1
        self.peak  = np.zeros(w, dtype=np.float32)  # peak w pikselach 0..h-1

    def update(self, features, dt):
        bands = features["bands"]
        w, h = self.w, self.h

        # resample bands -> 16 kolumn
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            src = np.arange(bands.shape[0])
            vals = np.interp(xi, src, bands).astype(np.float32)
        else:
            vals = bands.astype(np.float32)

        vals = np.clip(vals, 0.0, 1.0)
        target = vals * (h - 1)  # piksele

        # fizyka: szybkie “attack”, wolniejsze “fall”
        fall = float(dt) * 8.0       # opadanie słupka
        peak_fall = float(dt) * 3.0  # opadanie peaka

        for x in range(w):
            if target[x] > self.level[x]:
                self.level[x] = target[x]
            else:
                self.level[x] = max(0.0, self.level[x] - fall)

            self.peak[x] = max(self.peak[x], self.level[x])
            self.peak[x] = max(0.0, self.peak[x] - peak_fall)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = int(self.level[x])
            py = int(self.peak[x])

            # klasyczny kolor po X (tęcza jak na obrazku)
            hue = x / max(1, (w - 1))
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]

            # wypełnienie słupka (możesz dać lekkie przyciemnienie na dole)
            for y in range(hh + 1):
                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                # delikatny shading po wysokości (żeby nie było "flat")
                v = 0.55 + 0.45 * (y / max(1, h - 1))
                frame[idx] = (int(r * v), int(g * v), int(b * v))

            # peak-hold: biały pixel
            if 0 <= py < h:
                pidx = serpentine_index(x, py, w=w, h=h, origin_bottom=True)
                frame[pidx] = (255, 255, 255)

        return frame
