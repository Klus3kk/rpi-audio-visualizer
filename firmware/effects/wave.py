import numpy as np
from firmware.effects.bars import serpentine_index

class WaveEffect:
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h
        self.phase = 0.0

    def update(self, features, dt):
        w, h = self.w, self.h
        rms = float(features["rms"])
        bands = features["bands"]
        energy = float(np.mean(bands)) if bands is not None else 0.0

        self.phase += dt * (2.0 + 8.0 * energy)

        frame = [(0, 0, 0)] * (w * h)

        # prosta fala: środek + amplituda zależna od rms
        amp = int(round((h / 2 - 1) * min(1.0, rms * 8.0)))
        mid = (h - 1) // 2

        for x in range(w):
            y = mid + int(round(amp * np.sin(self.phase + (x * 0.6))))
            y = max(0, min(h - 1, y))
            idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
            frame[idx] = (80, 180, 255)

            # lekki “glow” pionowo
            if y + 1 < h:
                frame[serpentine_index(x, y + 1, w=w, h=h, origin_bottom=True)] = (20, 60, 120)
            if y - 1 >= 0:
                frame[serpentine_index(x, y - 1, w=w, h=h, origin_bottom=True)] = (20, 60, 120)

        return frame
