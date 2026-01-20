import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class SpiralEffect:
    """
    Rotating spiral vortex - bass controls rotation speed.
    Szybsza rotacja, więcej ramion spirali.
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.angle = 0.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02

            bands = safe_bands(features, 16)
            bass = float(np.mean(bands[:4]))
            mid  = float(np.mean(bands[4:12]))
            treble = float(np.mean(bands[12:]))

            intensity = float((params or {}).get("intensity", 0.75))

            # mocniejsza rotacja
            rotation_speed = 1.5 + 7.0 * bass * intensity + 2.5 * mid
            self.angle += dt * rotation_speed

            frame = blank_frame(self.w, self.h)

            cx, cy = (self.w - 1) / 2.0, (self.h - 1) / 2.0
            max_r = np.sqrt(cx * cx + cy * cy)

            for y in range(self.h):
                for x in range(self.w):
                    dx = x - cx
                    dy = y - cy

                    r = np.sqrt(dx * dx + dy * dy)
                    theta = np.arctan2(dy, dx)

                    # większa spirala
                    spiral = (theta + r * 0.85 - self.angle) % (2 * np.pi)

                    # grubsze ramiona + więcej światła
                    wave = np.sin(spiral * 4) * 0.5 + 0.5
                    radial = np.exp(- (r / (max_r * 0.9)) ** 2)

                    brightness = wave * radial
                    brightness *= (0.85 + 0.3 * treble)
                    brightness = min(1.0, brightness)

                    hue = (theta / (2 * np.pi) + mid * 0.35 + self.angle * 0.04) % 1.0
                    sat = 0.9
                    val = brightness * 0.45 * intensity  # JAŚNIEJ

                    r_c, g_c, b_c = colorsys.hsv_to_rgb(hue, sat, val)
                    frame[y * self.w + x] = (
                        int(r_c * 255),
                        int(g_c * 255),
                        int(b_c * 255),
                    )

            return frame
        except Exception:
            return blank_frame(self.w, self.h)
