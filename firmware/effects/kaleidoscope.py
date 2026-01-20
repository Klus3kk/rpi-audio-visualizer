import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class KaleidoscopeEffect:
    """
    Kaleidoscopic mandala - 8-fold symmetry, audio-reactive colors.
    Ciemniejsza, bardziej wyraźna wersja.
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
            
            # Szybsza rotacja na bass
            self.t += dt * (0.8 + 3.5 * bass)

            frame = blank_frame(self.w, self.h)

            cx, cy = (self.w - 1) / 2.0, (self.h - 1) / 2.0

            for y in range(self.h):
                for x in range(self.w):
                    dx = x - cx
                    dy = y - cy
                    
                    r = np.sqrt(dx * dx + dy * dy)
                    theta = np.arctan2(dy, dx)
                    
                    # 8-fold symmetry (więcej płatków)
                    n_folds = 8
                    theta_folded = (theta % (2 * np.pi / n_folds)) * n_folds
                    
                    # Pattern: wyraźniejsze pierścienie + linie radialne
                    ring_pattern = np.sin(r * 1.2 + self.t) * 0.5 + 0.5
                    radial_pattern = np.sin(theta_folded * 4 + self.t * 0.6) * 0.5 + 0.5
                    
                    # Ostrzejsze łączenie wzorów
                    pattern = np.maximum(ring_pattern * 0.7, radial_pattern * 0.3)
                    
                    # Audio-reactive colors
                    hue = (pattern * 0.6 + bass * 0.4 + mid * 0.2 + self.t * 0.1) % 1.0
                    sat = 0.9 + 0.1 * treble
                    
                    # Ciemniej - było 0.4, teraz max 0.22
                    val = pattern * 0.22 * intensity
                    
                    r_c, g_c, b_c = colorsys.hsv_to_rgb(hue, min(1.0, sat), val)
                    frame[y * self.w + x] = (int(r_c * 255), int(g_c * 255), int(b_c * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)