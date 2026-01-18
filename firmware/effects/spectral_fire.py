# firmware/effects/spectral_fire.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))

class SpectralFireEffect:
    """
    Spectral Fire v3:
    - mniej jasno (power + ograniczenie v)
    - lepsza reakcja na dźwięk (AGC + bass pulse + mniej noise)
    - stabilniejszy field (wygładzanie + sensowniejsze cooling)
    """

    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0

        self.field = np.zeros((self.h, self.w), dtype=np.float32)

        # AGC (auto-gain) – żeby ogień reagował także przy cichym audio
        self._gain = 1.0
        self._ref = 0.20  # docelowa średnia energii po wzmocnieniu (0.12..0.28)

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")

        # DOMYŚLNIE dużo mniej mocy niż 0.85
        power = float(params.get("power", 0.60))  # 0.50..0.75

        w, h = self.w, self.h

        bands = features.get("bands", None)
        if bands is None:
            return [(0, 0, 0)] * (w * h)

        bands = np.asarray(bands, dtype=np.float32)
        if bands.shape[0] != w:
            xi = np.linspace(0, bands.shape[0] - 1, w)
            base = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
        else:
            base = bands.astype(np.float32, copy=False)

        base = np.clip(base, 0.0, 1.0)

        # lekkie wygładzenie po X (mniej “iskrzenia” losowego)
        base = 0.20*np.roll(base, 1) + 0.60*base + 0.20*np.roll(base, -1)

        # gate, żeby cisza nie robiła “ognia”
        gate = 0.05
        base = (base - gate) / max(1e-6, (1.0 - gate))
        base = np.clip(base, 0.0, 1.0)

        # AGC na bazie średniej (nie max) – stabilne
        avg = float(np.mean(base))
        want = self._ref / max(1e-6, avg)
        want = max(0.7, min(3.0, want))

        # gain zmienia się wolno (bez “pompowania”)
        a = float(np.exp(-dt / 0.9))  # ~0.9s
        self._gain = self._gain * a + want * (1.0 - a)

        base = np.clip(base * self._gain, 0.0, 1.0)

        # bass pulse (bardziej “reakcja na beat”)
        bass = float(features.get("bass", float(np.mean(base[: max(1, w//5)]))))
        bass = _clamp01(bass * (0.90 + 1.10*intensity))

        # final injection signal: tekstura + puls
        inj = np.clip(
            (0.50 + 0.95*intensity) * base + (0.40 + 0.75*intensity) * bass,
            0.0, 1.0
        )


        # noise dużo mniejszy (wcześniej dominował)
        noise = (np.random.rand(w).astype(np.float32) * (0.03 + 0.05*(1.0-intensity)))

        # inject at bottom (y=0)
        # mniej pamięci, więcej odpowiedzi na inj
        self.field[0, :] = np.clip(
            0.55 * self.field[0, :] + 0.95 * inj + noise,
            0.0, 1.0
        )

        # propagate upward
        for y in range(1, h):
            arow = self.field[y - 1, :]

            left  = np.roll(arow, 1)
            right = np.roll(arow, -1)

            # blur/spread
            v = (arow + 0.55*left + 0.55*right) / (1.0 + 0.55 + 0.55)

            # cooling: mniej brutalny, ale rośnie z wysokością
            cool = (0.010 + 0.055*(1.0-intensity)) * (1.0 + 0.85*(y / max(1, h-1)))

            # update: mniej “zalegania”, bardziej “przepływ”
            self.field[y, :] = np.clip(
                0.82 * self.field[y, :] + 0.70 * v - cool,
                0.0, 1.0
            )

        frame = [(0, 0, 0)] * (w * h)

        mode = ("auto" if color_mode == "auto" else color_mode)

        # dodatkowe przycięcie jasności (żeby nie było za jasno nawet przy v~1)
        # zamiast v*1.15 (które robiło “white-ish”)
        for y in range(h):
            ty = self.t + y * 0.05
            for x in range(w):
                v = float(self.field[y, x])
                if v <= 0.02:
                    continue

                # kompresja jasności (mniej topów)
                vv = v ** 1.25  # >1 = ciemniej na górze zakresu
                vv = min(1.0, 0.85 * vv)

                frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = color_for(
                    vv, ty, mode=mode, power=power
                )

        return frame
