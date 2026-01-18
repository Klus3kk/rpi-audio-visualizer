import numpy as np
import colorsys

def serpentine_index(x, y, w=16, h=16, origin_bottom=True):
    # x: 0..w-1 (lewo->prawo)
    # y: 0..h-1 (dół->góra w logice efektu)
    if origin_bottom:
        y = (h - 1) - y
    if (y % 2) == 0:
        return y * w + x
    return y * w + (w - 1 - x)


class BarsEffect:
    """
    Filozofia:
    - X = częstotliwość (lewo->prawo)
    - Y = poziom (wysokość słupka)
    - Jasność (V w HSV) jest STAŁA i nie zależy od głośności.
      Głośność wpływa tylko na wysokość.
    - Cisza -> czarno (brak "tańca" po wyłączeniu mikrofonu)
    """

    def __init__(
        self,
        w=16,
        h=16,
        # stabilność:
        attack=0.55,          # 0..1 (większe = szybciej rośnie do targetu)
        decay_px_per_s=7.0,   # px/s opadania słupka
        peak_decay_px_per_s=3.5,
        # gate (żeby cisza była czarna):
        bar_gate=0.035,       # wartości bands < gate -> 0 (ustaw 0.02..0.06)
        # stała jasność koloru:
        hsv_v=0.35,           # stała "jasność" koloru 0..1 (niezależna od audio)
        hsv_s=1.0,            # saturacja
        # opcjonalnie: minimalny poziom jeśli ma być "delikatne tło" (u Ciebie raczej 0.0)
        floor_px=0.0,
    ):
        self.w = int(w)
        self.h = int(h)

        self.level = np.zeros(self.w, dtype=np.float32)  # w pikselach
        self.peak  = np.zeros(self.w, dtype=np.float32)

        self.attack = float(attack)
        self.decay = float(decay_px_per_s)
        self.peak_decay = float(peak_decay_px_per_s)

        self.bar_gate = float(bar_gate)

        self.hsv_v = float(hsv_v)
        self.hsv_s = float(hsv_s)
        self.floor_px = float(floor_px)

    def update(self, features, dt, params=None):
        # params opcjonalne (żeby pasowało do Twojego LedEngine)
        if params is None:
            params = {}

        intensity = float(params.get("intensity", 1.0))  # wpływa TYLKO na wysokość, nie na jasność
        w, h = self.w, self.h

        bands = features.get("bands", None)
        if bands is None:
            return [(0, 0, 0)] * (w * h)

        bands = np.asarray(bands, dtype=np.float32)

        # resample bands -> 16 kolumn
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            vals = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            vals = bands

        # clamp + gate (cisza = czarno)
        vals = np.clip(vals, 0.0, 1.0)
        vals[vals < self.bar_gate] = 0.0

        # intensywność wpływa na wysokość (ale nie na jasność koloru!)
        vals = np.clip(vals * (0.65 + 1.35 * intensity), 0.0, 1.0)

        # target w pikselach
        target = vals * (h - 1)

        # stabilizacja w czasie
        dt = float(dt)
        fall = self.decay * dt
        peak_fall = self.peak_decay * dt

        # attack: szybkie dojście do targetu bez skoków
        a = self.attack
        for x in range(w):
            if target[x] > self.level[x]:
                # interpolacja zamiast skoku
                self.level[x] = (1.0 - a) * self.level[x] + a * target[x]
            else:
                self.level[x] = max(self.floor_px, self.level[x] - fall)

            # peak
            if self.level[x] > self.peak[x]:
                self.peak[x] = self.level[x]
            else:
                self.peak[x] = max(self.floor_px, self.peak[x] - peak_fall)

        # budowa ramki
        frame = [(0, 0, 0)] * (w * h)

        # stała jasność koloru (V) = nie oślepia po puknięciu
        V = self.hsv_v
        S = self.hsv_s

        for x in range(w):
            hh = int(round(self.level[x]))
            py = int(round(self.peak[x]))

            # kolor po X (lewo->prawo)
            hue = x / max(1, (w - 1))
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, S, V)]

            # słupek: od dołu do hh
            if hh > 0:
                for y in range(hh + 1):
                    idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                    frame[idx] = (r, g, b)

            # peak: delikatnie jaśniejszy (ale dalej ograniczony)
            if 0 <= py < h and py > 0:
                pidx = serpentine_index(x, py, w=w, h=h, origin_bottom=True)
                frame[pidx] = (min(255, int(r * 1.35)),
                               min(255, int(g * 1.35)),
                               min(255, int(b * 1.35)))

        return frame
