import numpy as np
import colorsys

def XY(x, y, w=16):
    # raster: lewo->prawo, dół->góra (y=0 dół)
    return y * w + x

class BarsEffect:
    """
    - X: 16 pasm (0..20kHz, co 1250Hz) lewo->prawo
    - Y: wysokość od dołu (y=0 = najniższy rząd)
    - jasność NIE zależy od głośności: kolor zależy od (x,y), nie od amplitudy
    - cisza: target=0, ale słupki opadają (nie znikają natychmiast)
    - frame row-major: idx = y*w + x
    """

    def __init__(
        self,
        w=16, h=16,
        attack=0.60,
        decay_px_per_s=3.8,
        peak_decay_px_per_s=2.0,
        rms_gate=0.0012,
        gate=0.012,
        NOISE_FLOOR_DB=-95.0,
        RANGE_DB=75.0,
        band_hz=1250.0,
        fmax=20000.0,
        min_fill_rows=0,          # ustaw 2 jeśli chcesz zawsze 2 dolne rzędy przy sygnale
        palette7_hues=(0.00, 0.07, 0.14, 0.33, 0.50, 0.66, 0.83),
        s=1.0,
        v_base=0.14,
        v_top=0.30,
        peak_boost=1.10,
        power_limit=0.85,
    ):
        self.w, self.h = int(w), int(h)
        self.level = np.zeros(self.w, np.float32)
        self.peak  = np.zeros(self.w, np.float32)
        self.prev  = np.zeros(self.w, np.float32)

        self.attack = float(attack)
        self.decay = float(decay_px_per_s)
        self.peak_decay = float(peak_decay_px_per_s)

        self.rms_gate = float(rms_gate)
        self.gate = float(gate)

        self.NOISE_FLOOR_DB = float(NOISE_FLOOR_DB)
        self.RANGE_DB = float(RANGE_DB)
        self.band_hz = float(band_hz)
        self.fmax = float(fmax)

        self.min_fill_rows = int(min_fill_rows)
        self.palette7_hues = tuple(float(x) for x in palette7_hues)
        self.s = float(s)
        self.v_base = float(v_base)
        self.v_top = float(v_top)
        self.peak_boost = float(peak_boost)
        self.power_limit = float(power_limit)

        # 7 kolorów po X (przypisanie 16 kolumn do 7 “slotów”)
        self.hue_x = np.zeros(self.w, np.float32)
        for x in range(self.w):
            k = int(round((x / max(1, self.w - 1)) * 6))
            self.hue_x[x] = self.palette7_hues[max(0, min(6, k))]

        # gradient jasności po Y (stały, niezależny od audio)
        t = np.linspace(0.0, 1.0, self.h, dtype=np.float32)
        self.v_y = np.clip(self.v_base + t * (self.v_top - self.v_base), 0.0, 1.0)

    def _bands_1250hz_from_mag2(self, mag2, sr, nfft):
        nyq = 0.5 * sr
        fmax = min(self.fmax, nyq)
        hz_per_bin = sr / float(nfft)

        out = np.zeros(self.w, np.float32)
        for i in range(self.w):
            lo_hz = i * self.band_hz
            hi_hz = min((i + 1) * self.band_hz, fmax)
            lo = max(1, int(lo_hz / hz_per_bin))
            hi = min(int(hi_hz / hz_per_bin), mag2.shape[0] - 1)
            out[i] = float(np.mean(mag2[lo:hi])) if hi > lo else 0.0

        band_db = 10.0 * np.log10(out + 1e-12).astype(np.float32)
        vals = (band_db - self.NOISE_FLOOR_DB) / self.RANGE_DB
        return np.clip(vals, 0.0, 1.0)

    def update(self, features, dt, params=None):
        params = params or {}
        intensity = float(params.get("intensity", 1.0))
        dt = float(dt) if dt else 0.02

        sr = int(features.get("samplerate", 44100))
        nfft = int(features.get("nfft", 1024))
        rms = float(features.get("rms", 0.0))

        mag2 = features.get("mag", None)
        if mag2 is not None:
            vals = self._bands_1250hz_from_mag2(np.asarray(mag2, np.float32), sr, nfft)
        else:
            bands = features.get("bands", None)
            if bands is None:
                return [(0, 0, 0)] * (self.w * self.h)
            vals = np.asarray(bands, np.float32)
            if vals.shape[0] != self.w:
                xi = np.linspace(0, vals.shape[0] - 1, self.w)
                vals = np.interp(xi, np.arange(vals.shape[0]), vals).astype(np.float32)
            vals = np.clip(vals, 0.0, 1.0)

        # cisza -> target=0, ale NIE kasuj level/peak (ma opadać)
        if rms < self.rms_gate:
            vals[:] = 0.0

        # smoothing
        alpha = 0.28
        vals = (1.0 - alpha) * self.prev + alpha * vals
        self.prev = vals

        # gate
        vals = vals.copy()
        vals[vals < self.gate] = 0.0

        # intensity tylko wysokość
        vals = np.clip(vals * (0.75 + 1.25 * intensity), 0.0, 1.0)
        target = vals * (self.h - 1)

        fall = self.decay * dt
        pf = self.peak_decay * dt
        a = self.attack

        for x in range(self.w):
            if target[x] > self.level[x]:
                self.level[x] = (1.0 - a) * self.level[x] + a * target[x]
            else:
                self.level[x] = max(0.0, self.level[x] - fall)

            if self.level[x] > self.peak[x]:
                self.peak[x] = self.level[x]
            else:
                self.peak[x] = max(0.0, self.peak[x] - pf)

        frame = [(0, 0, 0)] * (self.w * self.h)

        has_signal = bool(np.max(vals) > 0.0)
        min_rows = self.min_fill_rows if has_signal else 0

        for x in range(self.w):
            hh = int(np.clip(np.round(self.level[x]), 0, self.h - 1))
            if min_rows > 0:
                hh = max(hh, min_rows - 1)

            hue = float(self.hue_x[x])

            # pełne wypełnienie od dołu
            for y in range(hh + 1):
                v = float(self.v_y[y])
                r, g, b = colorsys.hsv_to_rgb(hue, self.s, v)
                frame[XY(x, y, self.w)] = (
                    int(r * 255 * self.power_limit),
                    int(g * 255 * self.power_limit),
                    int(b * 255 * self.power_limit),
                )

            # peak (delikatny)
            py = int(np.clip(np.round(self.peak[x]), 0, self.h - 1))
            if py <= hh:
                idx = XY(x, py, self.w)
                rr, gg, bb = frame[idx]
                frame[idx] = (
                    min(255, int(rr * self.peak_boost)),
                    min(255, int(gg * self.peak_boost)),
                    min(255, int(bb * self.peak_boost)),
                )

        return frame
