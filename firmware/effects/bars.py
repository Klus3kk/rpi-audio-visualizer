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
        self.level = np.zeros(w, dtype=np.float32)
        self._silent_for = 0.0
        self._black = [(0,0,0)] * (w*h)

    def update(self, features, dt):
        w, h = self.w, self.h

        # --- silence => OFF ---
        rms = float(features.get("rms", 0.0))
        RMS_GATE = 0.012
        if rms < RMS_GATE or not np.isfinite(rms):
            self._silent_for += float(dt)
        else:
            self._silent_for = 0.0
        if self._silent_for > 0.12:
            self.level[:] = 0.0
            return self._black

        # --- use bands 1:1 (left->right) ---
        vals = features["bands"].astype(np.float32, copy=False)
        if vals.shape[0] != w:
            # jeśli kiedyś zmienisz bands !=16, wtedy dopiero resample
            xi = np.linspace(0, vals.shape[0]-1, w)
            vals = np.interp(xi, np.arange(vals.shape[0]), vals).astype(np.float32)

        vals = np.clip(vals, 0.0, 1.0)

        # band gate: ucina “twitch”
        BAND_GATE = 0.07
        vals = (vals - BAND_GATE) / max(1e-6, (1.0 - BAND_GATE))
        vals = np.clip(vals, 0.0, 1.0)

        # compression: pik nie wywali na full
        vals = np.power(vals, 0.55)   # mocna tolerancja na loud

        # hard ceiling na wysokość (żeby nigdy nie waliło na pełną matrycę po jednym puknięciu)
        MAX_HEIGHT = 0.85  # 85% wysokości max
        target = vals * (h - 1) * MAX_HEIGHT

        # smoothing attack/release
        attack_tau, release_tau = 0.04, 0.18
        a_att = float(np.exp(-dt / attack_tau))
        a_rel = float(np.exp(-dt / release_tau))

        for x in range(w):
            t = float(target[x])
            cur = float(self.level[x])
            if t > cur:
                self.level[x] = cur * a_att + t * (1.0 - a_att)
            else:
                self.level[x] = cur * a_rel + t * (1.0 - a_rel)

        # --- render: stała jasność kolorów (no audio-based brightness) ---
        frame = [(0,0,0)] * (w*h)

        for x in range(w):
            hh = float(self.level[x])
            full = int(hh)
            frac = hh - full

            hue = x / max(1, w-1)
            r,g,b = [int(c*255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]

            # stały “pixel brightness” (żeby nie oślepiało)
            PIXEL_V = 0.45  # 0..1, stałe
            r = int(r * PIXEL_V)
            g = int(g * PIXEL_V)
            b = int(b * PIXEL_V)

            for y in range(full + 1):
                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                frame[idx] = (r, g, b)

            topy = full + 1
            if 0 <= topy < h and frac > 0.05:
                idx = serpentine_index(x, topy, w=w, h=h, origin_bottom=True)
                frame[idx] = (int(r*frac), int(g*frac), int(b*frac))

        return frame
