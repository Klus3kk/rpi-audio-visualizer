import numpy as np

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
        self.peak = np.zeros(w, dtype=np.float32)

    def update(self, features, dt):
        bands = features["bands"]
        w, h = self.w, self.h

        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            src = np.arange(bands.shape[0])
            vals = np.interp(xi, src, bands)
        else:
            vals = bands

        vals = np.clip(vals, 0.0, 1.0)
        heights = np.round(vals * (h - 1)).astype(int)

        decay = float(dt) * 0.8
        self.peak = np.maximum(self.peak - decay, vals)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = int(heights[x])
            for y in range(hh + 1):
                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                v = y / max(1, (h - 1))
                r = int(20 + 180 * vals[x])
                g = int(30 + 200 * v)
                b = int(10 + 120 * (1.0 - v))
                frame[idx] = (r, g, b)

            py = int(round(self.peak[x] * (h - 1)))
            pidx = serpentine_index(x, py, w=w, h=h, origin_bottom=True)
            frame[pidx] = (255, 255, 255)

        return frame
