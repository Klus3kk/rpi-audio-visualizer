import numpy as np
import colorsys

class BarsEffect:
    """
    Filozofia:
    - X: 16 pasm częstotliwości (lewo->prawo, niskie->wysokie)
    - Y: poziom (wysokość)
    - Jasność STAŁA (nie rośnie po puknięciu w mikrofon).
      Audio wpływa tylko na wysokość.
    - Cisza = czarne (brak “tańca” po wyciszeniu).
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
        decay_px_per_s=9.0,       # px/s opadania
        peak_decay_px_per_s=5.0,
        # gate ciszy:
        gate=0.06,                # 0.02..0.12 (zależy od mikrofonu)
        # jasność stała:
        hsv_v=0.22,               # 0..1 (realnie 0.15..0.35)
        hsv_s=1.0,
        # pasma:
        band_hz=1250.0,           # 20k/16 = 1250 Hz
        fmax=20000.0,
        floor_px=0.0,
    ):
        self.w = int(w)
        self.h = int(h)

        self.level = np.zeros(self.w, dtype=np.float32)
        self.peak  = np.zeros(self.w, dtype=np.float32)

        self.attack = float(attack)
        self.decay = float(decay_px_per_s)
        self.peak_decay = float(peak_decay_px_per_s)

        self.gate = float(gate)
        self.hsv_v = float(hsv_v)
        self.hsv_s = float(hsv_s)

        self.band_hz = float(band_hz)
        self.fmax = float(fmax)
        self.floor_px = float(floor_px)

        # precompute stałych kolorów (żeby nie liczyć HSV w każdej klatce)
        self._colors = []
        for x in range(self.w):
            hue = x / max(1, self.w - 1)
            r, g, b = colorsys.hsv_to_rgb(hue, self.hsv_s, self.hsv_v)
            self._colors.append((int(r * 255), int(g * 255), int(b * 255)))

    def _bands_1250hz(self, mag: np.ndarray, sr: int, nfft: int) -> np.ndarray:
        """
        mag: |rfft|, length nfft//2 + 1, mag[0]=DC
        Zwraca 16 wartości 0..1, każda to energia w pasmie 1250 Hz.
        """
        nyq = sr * 0.5
        fmax = min(self.fmax, nyq)
        if fmax <= 0:
            return np.zeros(self.w, dtype=np.float32)

        # pasma: [0..1250), [1250..2500), ..., [18750..20000)
        out = np.zeros(self.w, dtype=np.float32)

        # freqs per bin
        hz_per_bin = sr / float(nfft)

        for i in range(self.w):
            lo_hz = i * self.band_hz
            hi_hz = min((i + 1) * self.band_hz, fmax)

            lo = int(np.floor(lo_hz / hz_per_bin))
            hi = int(np.floor(hi_hz / hz_per_bin))

            lo = max(1, lo)                  # pomijamy DC
            hi = min(hi, mag.shape[0] - 1)

            if hi <= lo:
                out[i] = 0.0
            else:
                out[i] = float(np.mean(mag[lo:hi]))

        # kompresja dynamiczna i normalizacja klatkowa (stabilniejsza niż goły mean)
        out = np.log1p(out).astype(np.float32)

        m = float(np.max(out))
        if m > 1e-9:
            out = out / m
        else:
            out[:] = 0.0

        return out

    def update(self, features, dt, params=None):
        if params is None:
            params = {}

        intensity = float(params.get("intensity", 1.0))  # wpływa tylko na wysokość
        sr = int(features.get("samplerate", 44100))
        nfft = int(features.get("nfft", 1024))

        # potrzebujemy FFT albo chociaż mag. Jeśli masz tylko bands w features -> użyj tego fallbackowo.
        mag = features.get("mag", None)  # jeśli dodasz w FeatureExtractor
        if mag is not None:
            mag = np.asarray(mag, dtype=np.float32)
            vals = self._bands_1250hz(mag, sr, nfft)
        else:
            # fallback: jak masz features["bands"] (np. geomspace), to tylko resampluj
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

        # gate ciszy (najważniejsze dla “nie rusza się po wyciszeniu”)
        vals[vals < self.gate] = 0.0

        # intensity tylko skaluje wysokość, NIE jasność
        vals = np.clip(vals * (0.55 + 1.45 * intensity), 0.0, 1.0)

        target = vals * (self.h - 1)

        dt = float(dt)
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

        for x in range(self.w):
            hh = int(round(self.level[x]))
            py = int(round(self.peak[x]))

            r, g, b = self._colors[x]

            if hh > 0:
                for y in range(hh + 1):
                    idx = y * self.w + x
                    frame[idx] = (r, g, b)

            if 0 <= py < self.h and py > 0:
                pidx = py * self.w + x
                # peak trochę jaśniejszy, ale nadal ograniczony
                frame[pidx] = (min(255, int(r * 1.25)),
                               min(255, int(g * 1.25)),
                               min(255, int(b * 1.25)))

        return frame
