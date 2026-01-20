import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class RippleEffect:
    """
    Concentric ripples emanating from center - beats trigger new ripples.
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0
        self.last_bass = 0.0
        self.ripples = []  # (birth_time, strength)

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            self.t += dt
            
            bands = safe_bands(features, 16)
            rms = safe_rms(features)
            bass = float(np.mean(bands[:4]))
            
            intensity = float((params or {}).get("intensity", 0.75))
            
            # Detect bass hits (trigger new ripples)
            if bass > self.last_bass + 0.15 and bass > 0.3:
                self.ripples.append((self.t, bass))
            self.last_bass = bass * 0.9 + self.last_bass * 0.1
            
            # Remove old ripples
            self.ripples = [(t, s) for (t, s) in self.ripples if self.t - t < 2.0]

            frame = blank_frame(self.w, self.h)

            cx, cy = (self.w - 1) / 2.0, (self.h - 1) / 2.0

            for y in range(self.h):
                for x in range(self.w):
                    dx = x - cx
                    dy = y - cy
                    r = np.sqrt(dx * dx + dy * dy)
                    
                    val = 0.0
                    
                    # Sum all active ripples
                    for (birth_t, strength) in self.ripples:
                        age = self.t - birth_t
                        ripple_r = age * 8.0  # wave speed
                        
                        # Distance from ripple ring
                        dist = abs(r - ripple_r)
                        
                        if dist < 2.0:
                            # Gaussian falloff
                            wave = np.exp(-dist * dist / 0.5)
                            fade = max(0.0, 1.0 - age / 2.0)  # fade over 2s
                            val += wave * fade * strength
                    
                    val = min(1.0, val) * intensity
                    
                    if val > 0.05:
                        # Color: cyan to blue
                        hue = 0.55 + val * 0.1
                        sat = 0.9
                        r, g, b = colorsys.hsv_to_rgb(hue, sat, val * 0.5)
                        frame[y * self.w + x] = (int(r * 255), int(g * 255), int(b * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)