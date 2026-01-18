# firmware/effects/wave.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

def _ema(prev: float, x: float, a: float) -> float:
    return prev * a + x * (1.0 - a)

class WaveEffect:
    """
    Wave (oscyloskop-linia) – poprawki:
    - większa "czułość" (mikrofon): soft-gain + auto-gain (AGC) na RMS
    - mniej chaotyczne: wygładzona amplituda + lekkie wygładzenie po X
    - nadal: bez flasha (power limiter), mapping serpentine_index(origin_bottom=True)
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.phase = 0.0
        self.t = 0.0

        # AGC na RMS
        self._gain = 1.0
        self._rms_ref = 0.030   # docelowy "rms po gain" (większe = bardziej czułe)
        self._amp_smooth = 0.0  # wygładzona amplituda

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        w, h = self.w, self.h
        intensity  = float(params.get("intensity", 0.80))
        color_mode = params.get("color_mode", "auto")
        power      = float(params.get("power", 0.55))   # ZMNIEJSZONE: mniej mocy
        glow       = float(params.get("glow", 0.22))    # ZMNIEJSZONE: mniej mocy

        # czułość (ustawiasz bez grzebania w feature extractorze)
        mic_gain   = float(params.get("mic_gain", 2.2)) # 1.0..4.0 (większe = czulsze)

        rms = float(features.get("rms", 0.0))
        bands = features.get("bands", None)
        energy = float(np.mean(bands)) if bands is not None else 0.0

        # ---- AGC (auto-gain) na RMS: zwiększa czułość na ciche sygnały, ale nie przepala ----
        # chcemy: (rms * mic_gain * gain) ~ rms_ref
        want = self._rms_ref / max(1e-6, rms * mic_gain)
        want = max(0.6, min(6.0, want))  # limiter
        a_g = float(np.exp(-dt / 0.70))  # wolne zmiany (brak pompowania)
        self._gain = _ema(self._gain, want, a_g)

        rms_eff = rms * mic_gain * self._gain
        rms_eff = min(0.25, rms_eff)     # twarde zabezpieczenie

        # speed (trochę spokojniej)
        self.phase += dt * (1.5 + 6.0 * energy * (0.25 + intensity))

        # amplitude (bardziej czułe, ale wygładzone)
        amp_target = (h / 2.0 - 1.0) * min(1.0, (rms_eff * 14.0) * (0.55 + 1.05 * intensity))

        a_amp = float(np.exp(-dt / 0.12))  # smoothing amplitudy
        self._amp_smooth = _ema(self._amp_smooth, amp_target, a_amp)

        amp = self._amp_smooth
        mid = (h - 1) / 2.0

        frame = [(0, 0, 0)] * (w * h)

        # lekki smoothing po X (żeby nie było szarpania)
        # zamiast czystej sin: dodaj małą drugą harmoniczną zależną od energii
        wobble = 0.25 + 0.35 * energy

        for x in range(w):
            y = mid + amp * (
                np.sin(self.phase + x * 0.58) +
                wobble * 0.35 * np.sin(1.7 * self.phase + x * 0.22)
            )
            y = int(round(y))
            if y < 0: y = 0
            if y >= h: y = h - 1

            # kolor: zależny od X + Y (ładniej niż stały)
            yk = abs(y - mid) / max(1e-6, mid)
            v = 0.16 + 0.52 * yk         # stałe w funkcji Y (bez flasha)
            c = color_for(v, self.t + 0.03 * x, mode=color_mode)  # palette ma już clamp
            # power limiter
            c = (int(c[0] * power), int(c[1] * power), int(c[2] * power))

            frame[serpentine_index(x, y, w=w, h=h, origin_bottom=True)] = c

            if glow > 0.0:
                gg = glow
                if y + 1 < h:
                    frame[serpentine_index(x, y + 1, w=w, h=h, origin_bottom=True)] = (
                        int(c[0] * gg), int(c[1] * gg), int(c[2] * gg)
                    )
                if y - 1 >= 0:
                    frame[serpentine_index(x, y - 1, w=w, h=h, origin_bottom=True)] = (
                        int(c[0] * gg), int(c[1] * gg), int(c[2] * gg)
                    )

        return frame
