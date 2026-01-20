import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class RippleEffect:
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0
        self.last_bass = 0.0
        self.ripples = []  # (birth_time, strength)
        self.color_phase = 0.0
        self.last_trigger_t = -999.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            self.t += dt

            self.color_phase += dt * 0.05

            bands = safe_bands(features, 16)
            rms = safe_rms(features)
            bass = float(np.mean(bands[:4]))
            mid = float(np.mean(bands[4:12]))

            p = (params or {})
            intensity = float(p.get("intensity", 0.75))

            # more frequent ripples
            cooldown = float(p.get("ripple_cooldown", 0.10))
            min_bass = float(p.get("ripple_min_bass", 0.18))
            delta = float(p.get("ripple_delta", 0.06))
            beat_th = float(p.get("ripple_beat_th", 0.28))

            self.last_bass = 0.65 * self.last_bass + 0.35 * bass
            beat = bass + 0.35 * mid

            if (self.t - self.last_trigger_t) > cooldown:
                if (bass > self.last_bass + delta and bass > min_bass) or (beat > beat_th):
                    self.ripples.append((self.t, beat))
                    self.last_trigger_t = self.t

            ttl = float(p.get("ripple_ttl", 2.2))
            self.ripples = [(t, s) for (t, s) in self.ripples if self.t - t < ttl]

            frame = blank_frame(self.w, self.h)
            cx, cy = (self.w - 1) / 2.0, (self.h - 1) / 2.0

            speed = float(p.get("ripple_speed", 10.5))
            ring_w = float(p.get("ripple_width", 2.3))
            gauss = float(p.get("ripple_gauss", 0.55))

            for y in range(self.h):
                for x in range(self.w):
                    dx = x - cx
                    dy = y - cy
                    r = np.sqrt(dx * dx + dy * dy)

                    val = 0.0
                    for (birth_t, strength) in self.ripples:
                        age = self.t - birth_t
                        ripple_r = age * speed
                        dist = abs(r - ripple_r)

                        if dist < ring_w:
                            wave = np.exp(-dist * dist / gauss)
                            fade = max(0.0, 1.0 - age / ttl)
                            val += wave * fade * strength

                    val = min(1.0, val) * intensity

                    if val > 0.05:
                        base_hue = 0.5 + 0.35 * np.sin(self.color_phase)
                        hue = (base_hue + mid * 0.1) % 1.0
                        sat = 0.9
                        brightness = val * 0.3

                        r_c, g_c, b_c = colorsys.hsv_to_rgb(hue, sat, brightness)
                        frame[y * self.w + x] = (int(r_c * 255), int(g_c * 255), int(b_c * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)
