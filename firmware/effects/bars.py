import numpy as np
import colorsys

class BarsEffect:
    """
    Filozofia:
    - X: 16 pasm częstotliwości (lewo->prawo, niskie->wysokie)
         pasmo i => [i*1250 .. (i+1)*1250] Hz, do 20kHz
    - Y: poziom (wysokość)
    - Jasność STAŁA (nie rośnie po puknięciu w mikrofon).
      Audio wpływa tylko na wysokość.
    - Cisza = target=0 i opadanie (bez “tańca”, ale też bez natychmiastowego znikania).
    - Mapowanie LED: efekt zwraca frame w porządku row-major:
        idx = y*w + x  (y=0 dół, y rośnie do góry)
      Serpentine robi ESP32.
    """

    def __init__(
        self,
        w=16,
        h=16,

        # reakcja:
        attack=0.55,              # 0..1, większe = szybciej rośnie do targetu
        decay_px_per_s=7.0,       # px/s opadania (mniejsze = wolniej opada)
        peak_decay_px_per_s=3.5,

        # cisza:
        rms_gate=0.012,           # RMS poniżej => silent
        gate=0.06,                # gate na pasmach (po normalizacji)

        # jasność stała:
        hsv_v=0.22,               # jasność słupka (0.15..0.35)
        hsv_s=1.0,

        # pasma:
        band_hz=1250.0,
        fmax=20000.0,
        floor_px=0.0,

        # stała skala pasm (żeby nie skakało między klatkami):
        NOISE_FLOOR_DB=-78.0,
        RANGE_DB=48.0,

        # gradient kolorów po Y:
        y_hue_shift=0.18,         # ile hue zmienia się od dołu do góry (0.10..0.30)
        peak_boost=1.20,          # peak delikatnie jaśniejszy (ale nadal limitowany)
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
        self.floor_px = float(floor_px)

        self.NOISE_FLOOR_DB = float(NOISE_FLOOR_DB)
        self.RANGE_DB = float(RANGE_DB)

        self.y_hue_shift = float(y_hue_shift)
        self.peak_boost = float(peak_boost)

        # bazowe hue per kolumna (X=pasmo), precompute
        self._hue_x = np.zeros(self.w, dtype=np.float32)
        for x in range(self.w):
            self._hue_x[x] = x / max(1, self.w - 1)

        # do wygładzania PASM (osobno od smoothing w FeatureExtractor)
        self._prev_vals = np.zeros(self.w, dtype=np.float32)

    def _bands_1250hz_from_mag2(self, mag2: np.ndarray, sr: int, nfft: int) -> np.ndarray:
        """
        mag2: power spectrum z rfft (real^2+imag^2), length nfft//2 + 1, mag2[0]=DC
        Zwraca 16 wartości 0..1, każda to energia w pasmie 1250 Hz, w stałej skali dB.
        """
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

            lo = max(1, lo)  # pomijamy DC
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

        intensity = float(params.get("intensity", 1.0))  # wpływa tylko na wysokość
        sr = int(features.get("samplerate", 44100))
        nfft = int(features.get("nfft", 1024))
        rms = float(features.get("rms", 0.0))

        dt = float(dt) if dt else 0.02

        silent = (rms < self.rms_gate)
        if silent:
            # kasujemy pamięć pasm, żeby po ciszy nie “pompowało” od szumu
            self._prev_vals *= 0.0

        # preferuj mag2 (power) z FeatureExtractor
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

        # jeśli cisza: target=0, ale level/peak opadają powoli (bez natychmiastowego resetu)
        if silent:
            vals[:] = 0.0

        # wygładzanie pasm (dla stabilności)
        alpha = 0.35
        vals = (1.0 - alpha) * self._prev_vals + alpha * vals
        self._prev_vals = vals

        # gate na pasmach (po wygładzeniu)
        vals = vals.copy()
        vals[vals < self.gate] = 0.0

        # intensity skaluje wysokość, NIE jasność
        vals = np.clip(vals * (0.55 + 1.45 * intensity), 0.0, 1.0)

        target = vals * (self.h - 1)

        fall = self.decay * dt
        peak_fall = self.peak_decay * dt
        a = self.attack

        for x in range(self.w):
            if target[x] > self.level[x]:
                self.level[x] = (1.0 - a) * self.level[x] + a * target[x]
            else:
                self.level[x] = max(self.floor_px, self.level[x] - fall)

            if self.level[x] > self.peak[x]:
                self.peak[x] = self.level[x]
            else:
                self.peak[x] = max(self.floor_px, self.peak[x] - peak_fall)

        # budowa ramki: row-major, y=0 dół
        frame = [(0, 0, 0)] * (self.w * self.h)

        S = self.hsv_s
        V = self.hsv_v

        for x in range(self.w):
            hue_base = float(self._hue_x[x])

            lvl = float(self.level[x])
            if lvl <= 0.0:
                continue

            # 1) start od y=0: floor zamiast round + rysujemy zawsze y=0..hh
            hh = int(np.floor(lvl + 1e-6))
            if hh < 0:
                hh = 0
            if hh > self.h - 1:
                hh = self.h - 1

            for y in range(hh + 1):
                t = y / max(1, (self.h - 1))
                hue = (hue_base + self.y_hue_shift * t) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, S, V)
                frame[y * self.w + x] = (int(r * 255), int(g * 255), int(b * 255))

            # peak
            py = int(np.floor(float(self.peak[x]) + 1e-6))
            if 0 < py < self.h:
                t = py / max(1, (self.h - 1))
                hue = (hue_base + self.y_hue_shift * t) % 1.0
                pr, pg, pb = colorsys.hsv_to_rgb(hue, S, min(1.0, V * self.peak_boost))
                frame[py * self.w + x] = (int(pr * 255), int(pg * 255), int(pb * 255))

        return frame
