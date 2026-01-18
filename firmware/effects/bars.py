import numpy as np
import colorsys

class BarsEffect:
    """
    - X: pasma 0..20kHz po 1250Hz (lewo->prawo w logice)
    - Y: wysokość (y=0 dół)
    - Stała jasność (audio nie podbija V), audio wpływa tylko na wysokość
    - 7 dyskretnych kolorów po X
    - Gradient po Y (ładne wypełnienie, nie „bloki”)
    - Opcjonalny x_map: mapuje logiczne kolumny na fizyczne (gdy taśma startuje inaczej)
    """

    def __init__(
        self,
        w=16, h=16,
        attack=0.60,
        decay_px_per_s=5.0,
        peak_decay_px_per_s=2.8,
        rms_gate=0.003,
        gate=0.02,
        band_hz=1250.0,
        fmax=20000.0,
        NOISE_FLOOR_DB=-85.0,
        RANGE_DB=60.0,

        # jasność stała (bazowa) + łagodny gradient po Y
        v_base=0.18,
        v_top=0.32,        # jasność na górze słupka (nadal niezależna od audio)
        s=1.0,

        # 7 kolorów
        palette7_hues=(0.00, 0.08, 0.16, 0.33, 0.50, 0.66, 0.83),

        # mapowanie kolumn (None = normalnie 0..15)
        x_map=None,
    ):
        self.w = int(w)
        self.h = int(h)

        self.level = np.zeros(self.w, dtype=np.float32)
        self.peak  = np.zeros(self.w, dtype=np.float32)

        self.attack = float(attack)
        self.decay = float(decay_px_per_s)
        self.peak_decay = float(peak_decay_px_per_s)

        self.rms_gate = float(rms_gate)
        self.gate = float(gate)

        self.band_hz = float(band_hz)
        self.fmax = float(fmax)
        self.NOISE_FLOOR_DB = float(NOISE_FLOOR_DB)
        self.RANGE_DB = float(RANGE_DB)

        self.v_base = float(v_base)
        self.v_top = float(v_top)
        self.s = float(s)

        self.palette7_hues = tuple(float(x) for x in palette7_hues)

        if x_map is None:
            self.x_map = list(range(self.w))
        else:
            xm = list(x_map)
            if len(xm) != self.w:
                raise ValueError("x_map must have length w=16")
            self.x_map = xm

        # band smoothing
        self._prev_vals = np.zeros(self.w, dtype=np.float32)

        # precompute V per Y (gradient)
        if self.h > 1:
            t = np.linspace(0.0, 1.0, self.h, dtype=np.float32)
        else:
            t = np.array([0.0], dtype=np.float32)
        self._v_y = (self.v_base + t * (self.v_top - self.v_base)).astype(np.float32)
        self._v_y = np.clip(self._v_y, 0.0, 1.0)

        # precompute hue per X (7 kolorów rozciągnięte na 16 kolumn)
        self._hue_x = np.zeros(self.w, dtype=np.float32)
        for x in range(self.w):
            # mapuj x do 0..6
            k = int(round((x / max(1, self.w - 1)) * 6))
            k = max(0, min(6, k))
            self._hue_x[x] = self.palette7_hues[k]

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

            lo = max(1, lo)
            hi = min(hi, mag2.shape[0] - 1)

            if hi <= lo:
                band_pow[i] = 0.0
            else:
                band_pow[i] = float(np.mean(mag2[lo:hi]))

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

        if silent:
            vals[:] = 0.0
            self._prev_vals *= 0.0

        # smoothing pasm
        alpha = 0.28
        vals = (1.0 - alpha) * self._prev_vals + alpha * vals
        self._prev_vals = vals

        # gate
        vals = vals.copy()
        vals[vals < self.gate] = 0.0

        # intensity tylko na wysokość
        vals = np.clip(vals * (0.60 + 1.40 * intensity), 0.0, 1.0)
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

        for x in range(self.w):
            hh = int(np.clip(np.round(self.level[x]), 0, self.h - 1))

            phys_x = self.x_map[x]  # klucz do „startuje od środka”
            hue = float(self._hue_x[x])

            # pełne wypełnienie + gradient po Y
            for y in range(hh + 1):
                v = float(self._v_y[y])
                r, g, b = colorsys.hsv_to_rgb(hue, self.s, v)
                frame[y * self.w + phys_x] = (int(r * 255), int(g * 255), int(b * 255))

        return frame
