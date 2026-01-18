import numpy as np
import colorsys

def serpentine_index(x, y, w=16, h=16, origin_bottom=True):
    if origin_bottom:
        y = (h - 1) - y
    if y % 2 == 0:
        return y * w + x
    return y * w + (w - 1 - x)

def _ema(prev, x, a):
    return prev * a + x * (1.0 - a)

class BarsEffect:
    """
    16 bars: 0..20kHz, each 1250Hz (left->right).
    Uses features["mag"] as mag2 (power spectrum from rfft).
    Coordinates: your serpentine_index().
    """

    def __init__(self, w=16, h=16, fmax=20000.0):
        self.w = int(w)
        self.h = int(h)
        self.fmax = float(fmax)

        self.level = np.zeros(self.w, dtype=np.float32)  # 0..h-1
        self.peak  = np.zeros(self.w, dtype=np.float32)

        # AGC state (tolerant loud sounds)
        self._gain = 1.0
        self._ref  = 0.22     # target avg after gate
        self._gain_tau = 0.9  # s

        # fixed dB mapping (no per-frame rescale)
        self.NOISE_DB = -82.0
        self.RANGE_DB = 80.0

        # motion
        self.attack_tau  = 0.05
        self.release_tau = 0.22
        self.peak_tau    = 0.40

        # gates
        self.rms_gate  = 0.0015   # below -> target=0 (but bars fall, not instant off)
        self.band_gate = 0.03     # after normalize

        # brightness control (constant-ish, no flash)
        self.v_base = 0.10
        self.v_top  = 0.26
        self.sat    = 1.0

        # 7-color palette across X (discrete, nicer than continuous rainbow)
        self.palette7_hues = (0.00, 0.07, 0.14, 0.33, 0.50, 0.66, 0.83)

        # precompute hue per column (7 buckets)
        self._hue_x = np.zeros(self.w, dtype=np.float32)
        for x in range(self.w):
            k = int(round((x / max(1, self.w - 1)) * 6))
            self._hue_x[x] = self.palette7_hues[max(0, min(6, k))]

        # precompute V per row (y=0 bottom)
        t = np.linspace(0.0, 1.0, self.h, dtype=np.float32)
        self._v_y = np.clip(self.v_base + t * (self.v_top - self.v_base), 0.0, 1.0)

    def _bands_1250hz_from_mag2(self, mag2: np.ndarray, sr: int, nfft: int) -> np.ndarray:
        """
        mag2: power spectrum (len nfft//2 + 1), mag2[0]=DC
        returns 16 vals 0..1 for [0..1250), [1250..2500), ... up to 20kHz
        """
        nyq = 0.5 * sr
        fmax = min(self.fmax, nyq)
        hz_per_bin = sr / float(nfft)

        out_pow = np.zeros(self.w, dtype=np.float32)
        for i in range(self.w):
            lo_hz = i * 1250.0
            hi_hz = min((i + 1) * 1250.0, fmax)

            lo = int(lo_hz / hz_per_bin)
            hi = int(hi_hz / hz_per_bin)

            lo = max(1, lo)  # skip DC
            hi = min(hi, mag2.shape[0] - 1)

            out_pow[i] = float(np.mean(mag2[lo:hi])) if hi > lo else 0.0

        band_db = 10.0 * np.log10(out_pow + 1e-12).astype(np.float32)
        vals = (band_db - self.NOISE_DB) / self.RANGE_DB
        return np.clip(vals, 0.0, 1.0)

    def update(self, features, dt, params=None):
        params = params or {}
        intensity = float(params.get("intensity", 1.0))

        dt = float(dt) if dt else 0.02
        dt = min(dt, 0.05)

        sr = int(features.get("samplerate", 44100))
        nfft = int(features.get("nfft", 1024))
        rms = float(features.get("rms", 0.0))

        mag2 = features.get("mag", None)  # u Ciebie to jest mag2
        if mag2 is None:
            # fallback (jakbyś kiedyś nie dawał FFT)
            bands = features.get("bands", None)
            if bands is None:
                return [(0, 0, 0)] * (self.w * self.h)
            vals = np.asarray(bands, dtype=np.float32)
            if vals.shape[0] != self.w:
                xi = np.linspace(0, vals.shape[0] - 1, self.w)
                vals = np.interp(xi, np.arange(vals.shape[0]), vals).astype(np.float32)
            vals = np.clip(vals, 0.0, 1.0)
        else:
            vals = self._bands_1250hz_from_mag2(np.asarray(mag2, dtype=np.float32), sr, nfft)

        # silence -> target=0, but bars fall slowly
        if rms < self.rms_gate:
            vals[:] = 0.0

        # spatial smoothing (kills single-column twitch)
        vals = 0.25 * np.roll(vals, 1) + 0.5 * vals + 0.25 * np.roll(vals, -1)

        # band gate
        vals = np.clip((vals - self.band_gate) / max(1e-6, 1.0 - self.band_gate), 0.0, 1.0)

        # AGC (robust: based on mean, not max)
        avg = float(np.mean(vals))
        want = self._ref / max(1e-6, avg)
        want = max(0.55, min(3.0, want))
        a_gain = float(np.exp(-dt / self._gain_tau))
        self._gain = _ema(self._gain, want, a_gain)
        vals = np.clip(vals * self._gain, 0.0, 1.0)

        # gentle compression (prevents “all of a sudden” top)
        vals = vals / (vals + 0.35)

        # intensity affects ONLY height
        vals = np.clip(vals * (0.80 + 1.20 * intensity), 0.0, 1.0)
        target = vals * (self.h - 1)

        # envelope follower for smooth motion
        a_att  = float(np.exp(-dt / self.attack_tau))
        a_rel  = float(np.exp(-dt / self.release_tau))
        a_peak = float(np.exp(-dt / self.peak_tau))

        for x in range(self.w):
            t = target[x]
            cur = self.level[x]
            cur = _ema(cur, t, a_att) if t > cur else _ema(cur, t, a_rel)
            self.level[x] = cur
            self.peak[x] = max(self.peak[x] * a_peak, cur)

        frame = [(0, 0, 0)] * (self.w * self.h)

        for x in range(self.w):
            hh = float(self.level[x])
            full = int(hh)
            frac = hh - full
            py = int(round(float(self.peak[x])))

            hue = float(self._hue_x[x])

            # full fill 0..full
            for y in range(0, min(full + 1, self.h)):
                # color depends on (x,y): hue from x, brightness from y
                v = float(self._v_y[y])
                r, g, b = colorsys.hsv_to_rgb(hue, self.sat, v)
                idx = serpentine_index(x, y, w=self.w, h=self.h, origin_bottom=True)
                frame[idx] = (int(r * 255), int(g * 255), int(b * 255))

            # fractional top pixel (smooth top)
            topy = full + 1
            if 0 <= topy < self.h and frac > 0.05:
                v = float(self._v_y[topy]) * frac
                r, g, b = colorsys.hsv_to_rgb(hue, self.sat, v)
                idx = serpentine_index(x, topy, w=self.w, h=self.h, origin_bottom=True)
                frame[idx] = (int(r * 255), int(g * 255), int(b * 255))

            # peak marker (same palette, slightly brighter, no white flash)
            if 0 <= py < self.h:
                idx = serpentine_index(x, py, w=self.w, h=self.h, origin_bottom=True)
                rr, gg, bb = frame[idx]
                frame[idx] = (min(255, int(rr * 1.18)),
                              min(255, int(gg * 1.18)),
                              min(255, int(bb * 1.18)))

        return frame
