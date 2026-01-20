import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class KaleidoscopeEffect:
    """
    Kaleidoscopic mandala - 6-fold symmetry, audio-reactive colors.
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            
            bands = safe_bands(features, 16)
            rms = safe_rms(features)
            bass = float(np.mean(bands[:4]))
            mid = float(np.mean(bands[4:12]))
            treble = float(np.mean(bands[12:]))
            
            intensity = float((params or {}).get("intensity", 0.75))
            
            self.t += dt * (0.5 + 2.0 * bass)

            frame = blank_frame(self.w, self.h)

            cx, cy = (self.w - 1) / 2.0, (self.h - 1) / 2.0

            for y in range(self.h):
                for x in range(self.w):
                    dx = x - cx
                    dy = y - cy
                    
                    r = np.sqrt(dx * dx + dy * dy)
                    theta = np.arctan2(dy, dx)
                    
                    # 6-fold symmetry
                    n_folds = 6
                    theta_folded = (theta % (2 * np.pi / n_folds)) * n_folds
                    
                    # Pattern: concentric rings + radial lines
                    ring_pattern = np.sin(r * 0.8 + self.t) * 0.5 + 0.5
                    radial_pattern = np.sin(theta_folded * 3 + self.t * 0.5) * 0.5 + 0.5
                    
                    pattern = (ring_pattern + radial_pattern) / 2.0
                    
                    # Audio-reactive colors
                    hue = (pattern + bass * 0.3 + mid * 0.2) % 1.0
                    sat = 0.8 + 0.2 * treble
                    val = pattern * 0.4 * intensity
                    
                    r_c, g_c, b_c = colorsys.hsv_to_rgb(hue, min(1.0, sat), val)
                    frame[y * self.w + x] = (int(r_c * 255), int(g_c * 255), int(b_c * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)