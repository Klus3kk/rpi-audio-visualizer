import numpy as np
import colorsys

def serpentine_index(x, y, w=16, h=16, origin_bottom=True):
    if origin_bottom:
        y = (h - 1) - y
    if y % 2 == 0:
        return y * w + x
    return y * w + (w - 1 - x)

def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))

def _ema(prev, x, a):
    return prev * a + x * (1.0 - a)

class BarsEffect:
    """
    Stable bars: 20Hz..20kHz left->right (depends on your log edges).
    - No per-frame rescaling artifacts (handled in FeatureExtractor).
    - AGC for loud sounds (tolerant).
    - Envelope follower for smooth motion.
    """
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h

        self.level = np.zeros(w, dtype=np.float32)  # 0..(h-1)
        self.peak  = np.zeros(w, dtype=np.float32)

        # AGC state
        self._gain = 1.0
        self._ref  = 0.18   # target “average” energy after gain

    def update(self, features, dt, params=None):
        bands = features["bands"]
        w, h = self.w, self.h

        # resample -> 16 columns
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands.astype(np.float32, copy=False)

        vals = np.clip(vals, 0.0, 1.0)

        # spatial smoothing (kills single-column twitch)
        vals = 0.25*np.roll(vals, 1) + 0.5*vals + 0.25*np.roll(vals, -1)

        # noise gate (keep silence calm)
        gate = 0.05
        vals = (vals - gate) / max(1e-6, (1.0 - gate))
        vals = np.clip(vals, 0.0, 1.0)

        # AGC based on robust average (not max)
        avg = float(np.mean(vals))
        # desired gain to push avg -> ref, limited
        want = self._ref / max(1e-6, avg)
        want = max(0.6, min(3.0, want))

        # slow gain changes (prevents pumping)
        # time-constant ~0.8s
        a = float(np.exp(-dt / 0.8))
        self._gain = _ema(self._gain, want, a)

        vals = np.clip(vals * self._gain, 0.0, 1.0)

        # gentle compression (tolerant for loud, less twitch for quiet)
        # gamma < 1 expands quiet; gamma >1 compresses quiet
        gamma = 0.75
        vals = np.power(vals, gamma).astype(np.float32)

        # map to pixel height (float)
        target = vals * (h - 1)

        # envelope follower (attack/release in seconds)
        attack_tau = 0.04   # fast rise
        release_tau = 0.18  # slower fall
        a_att = float(np.exp(-dt / attack_tau))
        a_rel = float(np.exp(-dt / release_tau))

        # peak fall time
        peak_tau = 0.35
        a_peak = float(np.exp(-dt / peak_tau))

        for x in range(w):
            t = target[x]
            cur = self.level[x]
            if t > cur:
                cur = _ema(cur, t, a_att)
            else:
                cur = _ema(cur, t, a_rel)
            self.level[x] = cur

            # peak hold
            self.peak[x] = max(self.peak[x] * a_peak, cur)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = float(self.level[x])          # 0..h-1 float
            py = int(round(float(self.peak[x])))

            hue = x / max(1, (w - 1))
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]

            full = int(hh)
            frac = hh - full

            # fill full pixels
            for y in range(full + 1):
                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                v = 0.55 + 0.45 * (y / max(1, h - 1))
                frame[idx] = (int(r * v), int(g * v), int(b * v))

            # fractional top pixel for smoothness
            topy = full + 1
            if 0 <= topy < h and frac > 0.05:
                idx = serpentine_index(x, topy, w=w, h=h, origin_bottom=True)
                v = (0.55 + 0.45 * (topy / max(1, h - 1))) * frac
                frame[idx] = (int(r * v), int(g * v), int(b * v))

            # peak pixel
            if 0 <= py < h:
                pidx = serpentine_index(x, py, w=w, h=h, origin_bottom=True)
                frame[pidx] = (255, 255, 255)

        return frame
