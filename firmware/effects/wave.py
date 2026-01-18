# firmware/effects/wave.py
import numpy as np
from firmware.effects.bars import serpentine_index
from firmware.effects.palette import color_for

def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))

class WaveEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.phase = 0.0
        self.t = 0.0

        # stan dla stabilności
        self._amp_smooth = 0.0

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        w, h = self.w, self.h
        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")
        power      = float(params.get("power", 0.55))   # mniejsza moc
        glow       = float(params.get("glow", 0.18))    # delikatniej

        rms = float(features.get("rms", 0.0))
        bands = features.get("bands", None)
        energy = float(np.mean(bands)) if bands is not None else 0.0

        # --- CZUŁOŚĆ (gain na RMS) ---
        # typowo telefon->mikrofon: rms bywa bardzo małe
        rms_gain = float(params.get("mic_gain", 18.0))  # 12..30
        a_raw = (rms * rms_gain) * (0.65 + 1.10 * intensity)

        # trochę energii z pasm, żeby nie było “martwe” przy niskim rms
        a_raw += 0.55 * energy * (0.35 + intensity)

        a_raw = _clamp01(a_raw)

        # smoothing amplitudy (żeby nie skakało)
        a = float(np.exp(-dt / 0.10))
        self._amp_smooth = self._amp_smooth * a + a_raw * (1.0 - a)

        amp = (h / 2.0 - 1.0) * self._amp_smooth
        mid = (h - 1) / 2.0

        # speed: zależne od energii, ale nie za szybko
        self.phase += dt * (1.6 + 6.0 * energy * (0.25 + intensity))

        frame = [(0, 0, 0)] * (w * h)

        for x in range(w):
            y = int(round(mid + amp * np.sin(self.phase + x * 0.60)))
            y = 0 if y < 0 else (h - 1 if y >= h else y)

            # ZAWSZE rysuj coś: jeśli cisza, linia będzie blisko mid
            v = 0.12 + 0.18 * (abs(y - mid) / max(1e-6, mid))  # niskie V
            c = color_for(v, self.t + 0.03 * x, mode=color_mode)
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