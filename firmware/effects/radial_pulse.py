# firmware/effects/radial_pulse.py
import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.bars import serpentine_index

class RadialPulseEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0

    def update(self, features, dt, params=None):
        params = params or {}
        dt = float(dt) if dt else 0.02
        self.t += dt

        intensity  = float(params.get("intensity", 0.75))
        color_mode = params.get("color_mode", "auto")
        power      = float(params.get("power", 0.85))  # global limiter

        w, h = self.w, self.h
        cx, cy = (w - 1) * 0.5, (h - 1) * 0.5

        bass   = float(features.get("bass", 0.0))
        mid    = float(features.get("mid", 0.0))
        treble = float(features.get("treble", 0.0))

        # promień + grubość + swirl sterowane pasmami
        r0 = 2.0 + 6.5 * bass * (0.5 + intensity)
        thickness = 0.9 + 1.8 * mid
        swirl = 1.2 + 2.8 * treble

        frame = [(0, 0, 0)] * (w * h)

        # mniej wywołań sqrt/atan2: nadal czytelnie, ale bez 2D bufora
        for y in range(h):
            dy = y - cy
            for x in range(w):
                dx = x - cx

                r = (dx*dx + dy*dy) ** 0.5
                ang = np.arctan2(dy, dx)

                wave = np.sin(ang * swirl + self.t * 3.2)
                dist = abs(r - (r0 + 1.2 * wave))

                v = 1.0 - dist / thickness
                if v <= 0.02:
                    continue

                # stała “moc” + intensity, bez flasha
                v = max(0.0, min(1.0, v * (0.25 + 0.75 * (0.4 + intensity))))

                idx = serpentine_index(x, y, w=w, h=h, origin_bottom=True)
                frame[idx] = color_for(v, self.t, mode=color_mode, power=power)

        return frame
