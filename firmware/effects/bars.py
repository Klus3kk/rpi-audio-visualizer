import numpy as np
import colorsys

class BarsEffect:
    """
    Filozofia:
    - X: 16 pasm (0..20kHz), lewo->prawo: niskie->wysokie, po 1250 Hz na kolumnę
    - Y: wysokość słupka (0..h-1), start od samego dołu (y=0)
    - Jasność stała (V w HSV) -> audio nie zwiększa jasności, tylko wysokość
    - Cisza: target=0, ale słupki opadają (decay), nie znikają natychmiast
    - Frame zwracany jako row-major:
        idx = y*w + x, gdzie y=0 to dolny rząd w logice efektu.
      Mapowanie serpentine + flip robi ESP32.
    """

    def __init__(
        self,
        w=16,
        h=16,
        # dynamika:
        attack=0.60,              # 0..1
        decay_px_per_s=6.0,       # wolniejsze opadanie = mniejsza liczba
        peak_decay_px_per_s=3.0,

        # cisza / stabilność:
        rms_gate=0.003,           # typowo dla USB mic (0.002..0.006)
        gate=0.02,                # gate po normalizacji pasm (0.01..0.05)

        # stała jasność:
        hsv_v=0.22,               # stała jasność (0.15..0.35)
        hsv_s=1.0,

        # pasma:
        band_hz=1250.0,
        fmax=20000.0,

        # stała skala dB:
        NOISE_FLOOR_DB=-85.0,
        RANGE_DB=60.0,

        # gradient po Y:
        y_hue_shift=0.10,         # ile przesunąć hue od dołu do góry (0..~0.25)
        y_v_boost=0.12,           # ile podbić V ku górze (bez audio, nadal stała per Y)
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

        self.hsv_v = float(hsv_v)
        self.hsv_s = float(hsv_s)

        self.band_hz = float(band_hz)
        self.fmax = float(fmax)

        self.NOISE_FLOOR_DB = float(NOISE_FLOOR_DB)
        self.RANGE_DB = float(RANGE_DB)

        self.y_hue_shift = float(y_hue_shift)
        self.y_v_boost = float(y_v_boost)

        # do wygładzania pasm
        self._prev_vals = np.zeros(self.w, dtype=np.float32)

        # precompute bazowego hue po X (częstotliwość)
        self._base_hue = np.array(
            [x / max(1, self.w - 1) for x in range(self.w)],
            dtype=np.float32
        )

        # precompute gradient (hue_shift i v_boost) po Y
        # y=0 dół -> najmniejsze, y=h-1 góra -> największe
        if self.h > 1:
            t = np.linspace(0.0, 1.0, self.h, dtype=np.float32)
        else:
            t = np.array([0.0], dtype=np.float32)
        self._y_hue = (t * self.y_hue_shift).astype(np.float32)
        self._y_v = (self.hsv_v + t * self.y_v_boost).astype(np.float32)
        self._y_v = np.clip(self._y_v, 0.0, 1.0)

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

            if hi <= lo:
                band_pow[i] = 0.0
            else:
                band_pow[i] = float(np.mean(mag2[lo:hi]))

        band_db = 10.0 * np.log10(band_pow + 1e-12).astype(np.float32)

        vals = (band_db - self.NOISE_FLOOR_DB) / self.RANGE_DB
        vals = np.clip(vals, 0.0, 1.0)
        return vals

    def update(self, features, dt, params=None):
        if params is None:
            params = {}

        intensity = float(params.get("intensity", 1.0))  # tylko wysokość
        sr = int(features.get("samplerate", 44100))
        nfft = int(features.get("nfft", 1024))
        rms = float(features.get("rms", 0.0))
        dt = float(dt) if dt else 0.02

        silent = (rms < self.rms_gate)

        mag2 = features.get("mag", None)
        if mag2 is not None:
            mag2 = np.asarray(mag2, dtype=np.float32)
            vals = self._bands_1250hz_from_mag2(mag2, sr, nfft)
        else:
            bands = features.get("bands", None)
            if bands is None:
                return [(0, 0, 0)] * (self.w * self.h)
            bands = np.asarray(bands, dtype=np.float32)
            if bands.shape[0] != self.w:
                xi = np.linspace(0, bands.shape[0] - 1, self.w)
                vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
            else:
                vals = bands
            vals = np.clip(vals, 0.0, 1.0)

        # jeśli cisza: target=0, ale opadanie zostaje
        if silent:
            vals[:] = 0.0
            self._prev_vals *= 0.0

        # wygładzanie pasm
        alpha = 0.30
        vals = (1.0 - alpha) * self._prev_vals + alpha * vals
        self._prev_vals = vals

        # gate
        vals = vals.copy()
        vals[vals < self.gate] = 0.0

        # intensity tylko wysokość
        vals = np.clip(vals * (0.55 + 1.45 * intensity), 0.0, 1.0)
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

        # frame: row-major, y=0 dół
        frame = [(0, 0, 0)] * (self.w * self.h)

        for x in range(self.w):
            hh = int(np.clip(np.round(self.level[x]), 0, self.h - 1))

            # pełne podświetlenie od dołu, START OD y=0
            for y in range(hh + 1):
                # kolor zależny od X (freq) i Y (wysokość)
                hcol = float(self._base_hue[x] + self._y_hue[y]) % 1.0
                vcol = float(self._y_v[y])
                r, g, b = colorsys.hsv_to_rgb(hcol, self.hsv_s, vcol)
                frame[y * self.w + x] = (int(r * 255), int(g * 255), int(b * 255))

        return frame
