import numpy as np
import colorsys

def serpentine_index(x, y, w=16, h=16, origin_bottom=True):
    if origin_bottom:
        y = (h - 1) - y
    if y % 2 == 0:
        return y * w + x
    return y * w + (w - 1 - x)

def _clamp01(a):
    return 0.0 if a < 0.0 else (1.0 if a > 1.0 else float(a))

class BarsEffect:
    """
    Philosophy:
    - if input is quiet / mic off => COMPLETELY STATIC (black, no jitter)
    - low->high left->right
    - smooth motion only when real signal is present
    - tolerant to loud sounds (compression)
    """
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h

        self.level = np.zeros(w, dtype=np.float32)

        # "silence detector"
        self._silent_for = 0.0

        # last frame for hard freeze (optional)
        self._black = [(0,0,0)] * (w*h)

    def update(self, features, dt):
        w, h = self.w, self.h

        # ---- 1) HARD silence logic (this is what you want) ----
        # When mic is off / disconnected, RMS will usually drop very low.
        rms = float(features.get("rms", 0.0))

        # Tune this. For many USB mics, silence RMS ~ 0.001..0.01.
        # If mic is "off" it can be 0.0 or random; we treat both as silence.
        RMS_GATE = 0.012

        if rms < RMS_GATE or not np.isfinite(rms):
            self._silent_for += float(dt)
        else:
            self._silent_for = 0.0

        # after 0.15s of silence => FORCE OFF immediately
        if self._silent_for > 0.15:
            self.level[:] = 0.0
            return self._black

        # ---- 2) get bands (already 0..1 from FeatureExtractor) ----
        bands = features["bands"]
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands.astype(np.float32, copy=False)

        vals = np.clip(vals, 0.0, 1.0)

        # ---- 3) suppress residual jitter (band gate) ----
        BAND_GATE = 0.06
        vals = (vals - BAND_GATE) / max(1e-6, (1.0 - BAND_GATE))
        vals = np.clip(vals, 0.0, 1.0)

        # ---- 4) tolerant to loud sounds (compression) ----
        # sqrt expands low levels a bit, compresses high peaks
        vals = np.sqrt(vals)

        # ---- 5) stable smoothing only while signal exists ----
        # attack fast, release slower; no peaks.
        attack_tau  = 0.03
        release_tau = 0.12
        a_att = float(np.exp(-dt / attack_tau))
        a_rel = float(np.exp(-dt / release_tau))

        target = vals * (h - 1)

        for x in range(w):
            t = target[x]
            cur = float(self.level[x])
            if t > cur:
                self.level[x] = cur * a_att + t * (1.0 - a_att)
            else:
                self.level[x] = cur * a_rel + t * (1.0 - a_rel)

        # ---- 6) render (classic rainbow, bottom->top fill) ----
        frame = [(0,0,0)] * (w*h)
        for x in range(w):
            hh = float(self.level[x])
            full = int(hh)
            frac = hh - full

            hue = x / max(1, w-1)
            r,g,b = [int(c*255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]

            # fill solid pixels
            for y in range(full + 1):
                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                frame[idx] = (r, g, b)

            # fractional top pixel for smoothness
            topy = full + 1
            if 0 <= topy < h and frac > 0.05:
                idx = serpentine_index(x, topy, w=w, h=h, origin_bottom=True)
                frame[idx] = (int(r*frac), int(g*frac), int(b*frac))

        return frame
