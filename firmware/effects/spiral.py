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
            rms = safe_rms(features)
            bass = float(np.mean(bands[:4]))
            mid = float(np.mean(bands[4:12]))
            treble = float(np.mean(bands[12:]))
            
            intensity = float((params or {}).get("intensity", 0.75))
            
            # Rotation speed - szybciej!
            rotation_speed = 1.0 + 5.5 * bass * intensity + 2.0 * mid
            self.angle += dt * rotation_speed

            frame = blank_frame(self.w, self.h)

            cx, cy = (self.w - 1) / 2.0, (self.h - 1) / 2.0

            for y in range(self.h):
                for x in range(self.w):
                    dx = x - cx
                    dy = y - cy
                    
                    # Polar coordinates
                    r = np.sqrt(dx * dx + dy * dy)
                    theta = np.arctan2(dy, dx)
                    
                    # Spiral formula - więcej ramion (0.4 -> 0.6)
                    spiral = (theta + r * 0.6 - self.angle) % (2 * np.pi)
                    
                    # Więcej fal spirali (3 -> 5)
                    brightness = (np.sin(spiral * 5) * 0.5 + 0.5) * (1.0 - r / (self.w * 0.7))
                    brightness = max(0.0, min(1.0, brightness))
                    
                    # Dodatkowa pulsacja od treble
                    brightness *= (0.8 + 0.2 * treble)
                    
                    # Color based on angle and audio
                    hue = (theta / (2 * np.pi) + mid * 0.4 + self.angle * 0.05) % 1.0
                    sat = 0.9
                    
                    # Ciemniej
                    val = brightness * 0.28 * intensity
                    
                    r_c, g_c, b_c = colorsys.hsv_to_rgb(hue, sat, val)
                    frame[y * self.w + x] = (int(r_c * 255), int(g_c * 255), int(b_c * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)