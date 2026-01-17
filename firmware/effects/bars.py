import numpy as np
import colorsys

def serpentine_index(x, y, w=16, h=16, origin_bottom=True):
    if origin_bottom:
        y = (h - 1) - y
    if y % 2 == 0:
        return y * w + x
    return y * w + (w - 1 - x)

def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)

class BarsEffect:
    """
    Bars 16x16 tuned for mic:
    - gate kills idle jitter
    - shaping compresses noise floor + balances bass/treble
    - "musical" mapping: columns grouped from low->high
    """
    def __init__(self, w=16, h=16):
        self.w = w
        self.h = h
        self.level = np.zeros(w, dtype=np.float32)  # 0..h-1
        self.peak  = np.zeros(w, dtype=np.float32)

        # optional: idle freeze
        self._idle_timer = 0.0
        self._last_frame = [(0,0,0)] * (w*h)

    def _prep_vals(self, bands):
        w = self.w

        # resample bands -> 16 columns
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands.astype(np.float32, copy=False)

        vals = np.clip(vals, 0.0, 1.0)

        # --- 1) noise gate (critical for mic) ---
        # below gate => 0 (no movement)
        gate = 0.08
        vals = (vals - gate) / max(1e-6, (1.0 - gate))
        vals = np.clip(vals, 0.0, 1.0)

        # --- 2) dynamic shaping / compression ---
        # reduce micro jitter, keep transients
        vals = _smoothstep(vals)

        # --- 3) spectral tilt compensation ---
        # mic noise often lights highs; give lows a bit more weight, highs less
        # weights from left(low) to right(high)
        x = np.linspace(0.0, 1.0, w).astype(np.float32)
        # 1.15 at bass -> 0.75 at treble
        weights = 1.15 - 0.40 * x
        vals = np.clip(vals * weights, 0.0, 1.0)

        # --- 4) group smoothing across columns ---
        # prevents "salt & pepper" dancing
        vals = 0.25*np.roll(vals,1) + 0.5*vals + 0.25*np.roll(vals,-1)

        return np.clip(vals, 0.0, 1.0)

    def update(self, features, dt):
        bands = features["bands"]
        w, h = self.w, self.h

        vals = self._prep_vals(bands)

        # global idle detection: if everything quiet, freeze (optional)
        energy = float(np.mean(vals))
        if energy < 0.02:
            self._idle_timer += float(dt)
        else:
            self._idle_timer = 0.0

        # if quiet for a moment, return last frame (stops constant micro-movement)
        if self._idle_timer > 0.35:
            return self._last_frame

        target = vals * (h - 1)

        # physics: separate attack/fall using dt (stable at any fps)
        # attack is implicit: immediate rise. fall controls stability.
        fall = float(dt) * 5.0          # was 8.0 (too twitchy for mic)
        peak_fall = float(dt) * 2.0     # was 3.0

        for x in range(w):
            t = target[x]
            if t > self.level[x]:
                # controlled attack: not infinite jump (reduces flicker)
                self.level[x] = self.level[x] + (t - self.level[x]) * min(1.0, float(dt) * 20.0)
            else:
                self.level[x] = max(0.0, self.level[x] - fall)

            self.peak[x] = max(self.peak[x], self.level[x])
            self.peak[x] = max(0.0, self.peak[x] - peak_fall)

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            hh = int(self.level[x])
            py = int(self.peak[x])

            # hue by X (keeps your rainbow look)
            hue = x / max(1, (w - 1))
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]

            # fill bar
            for y in range(hh + 1):
                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                v = 0.55 + 0.45 * (y / max(1, h - 1))
                frame[idx] = (int(r * v), int(g * v), int(b * v))

            # peak hold
            if 0 <= py < h:
                pidx = serpentine_index(x, py, w=w, h=h, origin_bottom=True)
                frame[pidx] = (255, 255, 255)

        self._last_frame = frame
        return frame
