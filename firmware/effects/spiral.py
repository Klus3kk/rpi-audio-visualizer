import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class SpiralEffect:
    """
    Rotating spiral vortex - bass controls rotation speed.
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
            
            intensity = float((params or {}).get("intensity", 0.75))
            
            # Rotation speed based on bass
            rotation_speed = 0.5 + 3.0 * bass * intensity
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
                    
                    # Spiral formula
                    spiral = (theta + r * 0.4 - self.angle) % (2 * np.pi)
                    
                    # Brightness based on spiral + distance
                    brightness = (np.sin(spiral * 3) * 0.5 + 0.5) * (1.0 - r / (self.w * 0.7))
                    brightness = max(0.0, min(1.0, brightness))
                    
                    # Color based on angle and audio
                    hue = (theta / (2 * np.pi) + mid * 0.3) % 1.0
                    sat = 0.9
                    val = brightness * 0.4 * intensity
                    
                    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
                    frame[y * self.w + x] = (int(r * 255), int(g * 255), int(b * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)