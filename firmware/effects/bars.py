# firmware/effects/bars.py
import numpy as np
import colorsys

def serpentine_index(x, y, w=16, h=16, origin_bottom=True):
    """
    Zwraca indeks fizyczny LED dla macierzy 16x16 w układzie serpentine.
    origin_bottom=True => y=0 jest dołem (logika efektu).
    """
    x = int(x); y = int(y)
    if origin_bottom:
        y = (h - 1) - y
    if y % 2 == 0:
        return y * w + x
    return y * w + (w - 1 - x)

# alias, żebyś mógł pisać idx_serp jak w rozmowie
idx_serp = serpentine_index


class BarsEffect:
    """
    Filozofia:
    - X: 16 pasm 0..20kHz po 1250Hz (low->high)
    - Y: start od dołu
    - jasność stała (po Y), audio steruje wysokością
    - cisza: opadanie, nie “kasuj od razu”
    """

    def __init__(
        self,
        w=16, h=16,

        # dynamika
        attack=0.55,
        decay_px_per_s=3.8,
        rms_gate=0.003,
        gate=0.02,

        # pasma
        band_hz=1250.0,
        fmax=20000.0,
        NOISE_FLOOR_DB=-85.0,
        RANGE_DB=60.0,

        # kolory (7 kolorów) + gradient po Y
        palette7_hues=(0.00, 0.07, 0.14, 0.33, 0.50, 0.66, 0.83),
        s=1.0,
        v_base=0.06,      # dużo mniej mocy
        v_top=0.18,       # dużo mniej mocy
        power=0.70,       # globalny limiter
        y_hue_shift=0.08, # delikatny shift po Y

        # żeby “barsy” nie znikały natychmiast
        min_hold_s=0.20,  # ile czasu trzyma “sygnał” po ciszy
    ):
        self.w = int(w); self.h = int(h)

        self.level = np.zeros(self.w, dtype=np.float32)
        self.prev = np.zeros(self.w, dtype=np.float32)

        self.attack = float(attack)
        self.decay = float(decay_px_per_s)
        self.rms_gate = float(rms_gate)
        self.gate = float(gate)

        self.band_hz = float(band_hz)
        self.fmax = float(fmax)
        self.NOISE_FLOOR_DB = float(NOISE_FLOOR_DB)
        self.RANGE_DB = float(RANGE_DB)

        self.palette7_hues = tuple(float(x) for x in palette7_hues)
        self.s = float(s)
        self.v_base = float(v_base)
        self.v_top = float(v_top)
        self.power = float(power)
        self.y_hue_shift = float(y_hue_shift)

        self._signal_timer = 0.0
        self._min_hold_s = float(min_hold_s)

        # hue po X: 7 kolorów rozciągnięte na 16 kolumn
        self._hue_x = np.zeros(self.w, dtype=np.float32)
        for x in range(self.w):
            k = int(round((x / max(1, self.w - 1)) * 6))
            k = 0 if k < 0 else (6 if k > 6 else k)
            self._hue_x[x] = self.palette7_hues[k]

        # V po Y (stały gradient)
        t = np.linspace(0.0, 1.0, self.h, dtype=np.float32) if self.h > 1 else np.array([0.0], np.float32)
        self._v_y = np.clip(self.v_base + t * (self.v_top - self.v_base), 0.0, 1.0)
        self._y_hue = (t * self.y_hue_shift).astype(np.float32)

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
            lo = max(1, int(lo_hz / hz_per_bin))
            hi = min(int(hi_hz / hz_per_bin), mag2.shape[0] - 1)
            band_pow[i] = float(np.mean(mag2[lo:hi])) if hi > lo else 0.0

        band_db = 10.0 * np.log10(band_pow + 1e-12).astype(np.float32)
        vals = (band_db - self.NOISE_FLOOR_DB) / self.RANGE_DB
        return np.clip(vals, 0.0, 1.0)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        intensity = float(params.get("intensity", 0.75))

        sr = int(features.get("samplerate", 44100))
        nfft = int(features.get("nfft", 1024))
        rms = float(features.get("rms", 0.0))

        mag2 = features.get("mag", None)
        if mag2 is not None:
            vals = self._bands_1250hz_from_mag2(np.asarray(mag2, np.float32), sr, nfft)
        else:
            bands = features.get("bands", None)
            if bands is None:
                return [(0,0,0)] * (self.w*self.h)
            vals = np.asarray(bands, np.float32)
            if vals.shape[0] != self.w:
                xi = np.linspace(0, vals.shape[0]-1, self.w)
                vals = np.interp(xi, np.arange(vals.shape[0]), vals).astype(np.float32)
            vals = np.clip(vals, 0.0, 1.0)

        # “hold” sygnału po ciszy
        if rms >= self.rms_gate:
            self._signal_timer = self._min_hold_s
        else:
            self._signal_timer = max(0.0, self._signal_timer - dt)

        if self._signal_timer <= 0.0:
            vals[:] = 0.0  # target=0, ale level opada (nie resetujemy level)

        # smoothing pasm (stabilniej)
        alpha = 0.22
        vals = (1.0 - alpha) * self.prev + alpha * vals
        self.prev = vals

        # gate
        vals = vals.copy()
        vals[vals < self.gate] = 0.0

        # intensity tylko wysokość (delikatnie)
        vals = np.clip(vals * (0.55 + 1.05 * intensity), 0.0, 1.0)
        target = vals * (self.h - 1)

        # envelope
        fall = self.decay * dt
        a = self.attack
        for x in range(self.w):
            if target[x] > self.level[x]:
                self.level[x] = (1.0 - a) * self.level[x] + a * target[x]
            else:
                self.level[x] = max(0.0, self.level[x] - fall)

        frame = [(0,0,0)] * (self.w*self.h)

        for x in range(self.w):
            hh = int(np.clip(np.round(self.level[x]), 0, self.h - 1))
            hue_base = float(self._hue_x[x])
            for y in range(hh + 1):
                hcol = (hue_base + float(self._y_hue[y])) % 1.0
                vcol = float(self._v_y[y])
                r,g,b = colorsys.hsv_to_rgb(hcol, self.s, vcol)
                frame[serpentine_index(x, y, w=self.w, h=self.h, origin_bottom=True)] = (
                    int(r * 255 * self.power),
                    int(g * 255 * self.power),
                    int(b * 255 * self.power),
                )

        return frame
