import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class PlasmaEffect:
    """
    Animated plasma effect - psychedelic flowing colors.
    Audio reactivity: bass controls speed, bands control color shift.
    DIMMED VERSION - nie oślepia
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
            
            intensity = float((params or {}).get("intensity", 0.75))
            
            # Speed controlled by bass (szybciej)
            speed = 1.2 + 5.0 * bass * intensity
            self.t += dt * speed

            frame = blank_frame(self.w, self.h)

            for y in range(self.h):
                for x in range(self.w):
                    # Classic plasma formula (więcej fal)
                    v1 = np.sin(x * 0.6 + self.t)
                    v2 = np.sin(y * 0.6 + self.t * 1.4)
                    v3 = np.sin((x + y) * 0.3 + self.t * 0.8)
                    v4 = np.sin(np.sqrt(x*x + y*y) * 0.4 + self.t * 1.6)
                    
                    plasma = (v1 + v2 + v3 + v4) / 4.0
                    
                    # Map to color (hue shift based on audio)
                    hue = (plasma * 0.5 + 0.5 + bass * 0.4 + mid * 0.2) % 1.0
                    sat = 0.85 + 0.15 * rms * 4.0
                    
                    # DUŻO CIEMNIEJ - było 0.3 + 0.4, teraz max 0.25
                    val = 0.08 + 0.17 * intensity
                    
                    r, g, b = colorsys.hsv_to_rgb(hue, min(1.0, sat), val)
                    frame[y * self.w + x] = (int(r * 255), int(g * 255), int(b * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)