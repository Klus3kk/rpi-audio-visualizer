import numpy as np
import colorsys


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


class BarsEffect:
    """
    - X: 16 pasm (po 1250 Hz) lewo->prawo
    - Y: wysokość od dołu (y=0 = najniższy rząd)
    - jasność NIE zależy od głośności (stały gradient po Y)
    - cisza = target=0, ale level/peak opadają powoli
    - frame row-major: idx = y*w + x  (ESP nie powinno już nic “mieszać” poza serpentine)
    """

    def __init__(
        self,
        w=16,
        h=16,

        # reakcja
        attack=0.60,
        decay_px_per_s=3.8,
        peak_decay_px_per_s=2.0,

        # cisza
        rms_gate=0.0012,
        gate=0.012,

        # pasma
        band_hz=1250.0,
        fmax=20000.0,
        NOISE_FLOOR_DB=-95.0,
        RANGE_DB=75.0,

        # minimalne “dwa poziomy na dole” gdy jest sygnał
        min_fill_rows=2,

        # 7 kolorów bazowych (hue 0..1) — będą interpolowane po X
        palette7_hues=(0.00, 0.07, 0.14, 0.33, 0.50, 0.66, 0.83),

        s=1.0,

        # gradient jasności po Y (stały, niezależny od audio)
        v_base=0.10,
        v_top=0.26,

        # peak delikatny
        peak_boost=1.08,

        # stały limiter mocy w efekcie (niezależny od audio)
        power_limit=0.80,
    ):
        self.w = int(w)
        self.h = int(h)

        self.level = np.zeros(self.w, dtype=np.float32)
        self.peak = np.zeros(self.w, dtype=np.float32)
        self._prev_vals = np.zeros(self.w, dtype=np.float32)

        self.attack = float(attack)
        self.decay = float(decay_px_per_s)
        self.peak_decay = float(peak_decay_px_per_s)

        self.rms_gate = float(rms_gate)
        self.gate = float(gate)

        self.band_hz = float(band_hz)
        self.fmax = float(fmax)
        self.NOISE_FLOOR_DB = float(NOISE_FLOOR_DB)
        self.RANGE_DB = float(RANGE_DB)

        self.min_fill_rows = int(min_fill_rows)

        self.palette7_hues = np.array([float(x) for x in palette7_hues], dtype=np.float32)
        self.s = float(s)

        self.v_base = float(v_base)
        self.v_top = float(v_top)

        self.peak_boost = float(peak_boost)
        self.power_limit = float(power_limit)

        # gradient V po Y (y=0 dół)
        t = np.linspace(0.0, 1.0, self.h, dtype=np.float32)
        self._v_y = np.clip(self.v_base + t * (self.v_top - self.v_base), 0.0, 1.0)

        # hue po X: interpolacja 7->16 (żeby nie było “bloków”)
        x = np.linspace(0.0, 6.0, self.w, dtype=np.float32)  # 0..6
        k0 = np.floor(x).astype(np.int32)
        k1 = np.clip(k0 + 1, 0, 6)
        frac = x - k0
        self._hue_x = (1.0 - frac) * self.palette7_hues[k0] + frac * self.palette7_hues[k1]
        self._hue_x = np.clip(self._hue_x, 0.0, 1.0)

    def _bands_1250hz_from_mag2(self, mag2: np.ndarray, sr: int, nfft: int) -> np.ndarray:
        nyq = sr * 0.5
        fmax = min(self.fmax, nyq)
        if fmax <= 0:
            return np.zeros(self.w, dtype=np.float32)

        hz_per_bin = sr / float(nfft)

        band_pow = np.zeros(self.w, dtype=np.float32)
        for i in range(self.w):
            lo_hz = i * self.band_hz
            hi_hz = min((i + 1) * self.band_hz, fmax)

            lo = int(np.floor(lo_hz / hz_per_bin))
            hi = int(np.floor(hi_hz / hz_per_bin))

            lo = max(1, lo)  # bez DC
            hi = min(hi, mag2.shape[0] - 1)

            if hi > lo:
                band_pow[i] = float(np.mean(mag2[lo:hi]))
            else:
                band_pow[i] = 0.0

        band_db = 10.0 * np.log10(band_pow + 1e-12).astype(np.float32)
        vals = (band_db - self.NOISE_FLOOR_DB) / self.RANGE_DB
        return np.clip(vals, 0.0, 1.0)

    def update(self, features, dt, params=None):
        if params is None:
            params = {}

        intensity = float(params.get("intensity", 1.0))
        sr = int(features.get("samplerate", 44100))
        nfft = int(features.get("nfft", 1024))
        rms = float(features.get("rms", 0.0))
        dt = float(dt) if dt else 0.02

        silent = (rms < self.rms_gate)

        mag2 = features.get("mag", None)
        if mag2 is not None:
            vals = self._bands_1250hz_from_mag2(np.asarray(mag2, dtype=np.float32), sr, nfft)
        else:
            bands = features.get("bands", None)
            if bands is None:
                return [(0, 0, 0)] * (self.w * self.h)
            vals = np.asarray(bands, dtype=np.float32)
            if vals.shape[0] != self.w:
                xi = np.linspace(0, vals.shape[0] - 1, self.w)
                vals = np.interp(xi, np.arange(vals.shape[0]), vals).astype(np.float32)
            vals = np.clip(vals, 0.0, 1.0)

        # cisza: target=0, ale bez zerowania level/peak (ma opaść)
        if silent:
            vals[:] = 0.0
            self._prev_vals *= 0.0

        # smoothing pasm
        alpha = 0.28
        vals = (1.0 - alpha) * self._prev_vals + alpha * vals
        self._prev_vals = vals

        # gate na pasmach
        vals = vals.copy()
        vals[vals < self.gate] = 0.0

        # intensity tylko skaluje wysokość
        vals = np.clip(vals * (0.75 + 1.25 * intensity), 0.0, 1.0)

        target = vals * (self.h - 1)

        fall = self.decay * dt
        peak_fall = self.peak_decay * dt
        a = self.attack

        for x in range(self.w):
            if target[x] > self.level[x]:
                self.level[x] = (1.0 - a) * self.level[x] + a * target[x]
            else:
                self.level[x] = max(0.0, self.level[x] - fall)

            if self.level[x] > self.peak[x]:
                self.peak[x] = self.level[x]
            else:
                self.peak[x] = max(0.0, self.peak[x] - peak_fall)

        frame = [(0, 0, 0)] * (self.w * self.h)

        has_signal = bool(np.max(vals) > 0.0)
        min_rows = self.min_fill_rows if has_signal else 0

        for x in range(self.w):
            hh = int(np.clip(np.round(self.level[x]), 0, self.h - 1))
            if min_rows > 0 and hh < (min_rows - 1):
                hh = min_rows - 1

            hue = float(self._hue_x[x])

            # pełne wypełnienie od dołu
            for y in range(0, hh + 1):
                v = float(self._v_y[y])
                r, g, b = colorsys.hsv_to_rgb(hue, self.s, v)

                r = int(r * 255 * self.power_limit)
                g = int(g * 255 * self.power_limit)
                b = int(b * 255 * self.power_limit)

                frame[y * self.w + x] = (r, g, b)

            # peak delikatny
            py = int(np.clip(np.round(self.peak[x]), 0, self.h - 1))
            if 0 <= py <= hh:
                idx = py * self.w + x
                rr, gg, bb = frame[idx]
                frame[idx] = (
                    min(255, int(rr * self.peak_boost)),
                    min(255, int(gg * self.peak_boost)),
                    min(255, int(bb * self.peak_boost)),
                )

        return frame
