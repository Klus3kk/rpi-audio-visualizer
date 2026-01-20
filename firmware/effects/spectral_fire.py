import numpy as np
from firmware.effects.palette import color_for
from firmware.effects.common import safe_bands, blank_frame

class SpectralFireEffect:
    """
    Spectral fire - frequency bands as rising flames.
    Ulepszona wersja: płynniejsze, bardziej realistyczne płomienie.
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.field = np.zeros((h, w), np.float32)
        self.t = 0.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            self.t += dt
            
            bands = safe_bands(features, self.w)
            intensity = float((params or {}).get("intensity", 0.75))
            
            # Scroll field up (fire rises)
            self.field[1:] = self.field[:-1]
            
            # New bottom row - bands + random flicker
            flicker = np.random.rand(self.w) * 0.08
            self.field[0] = np.clip(bands * (0.8 + intensity * 0.4) + flicker, 0, 1)
            
            # Blur/spread fire (heat diffusion)
            # Horizontal blur
            field_blur = self.field.copy()
            field_blur[:, 1:] = (field_blur[:, 1:] + self.field[:, :-1]) * 0.5
            field_blur[:, :-1] = (field_blur[:, :-1] + self.field[:, 1:]) * 0.5
            
            # Vertical blur + cooling
            self.field = field_blur * 0.92  # cooling factor
            
            # Clip
            self.field = np.clip(self.field, 0, 1)

            frame = blank_frame(self.w, self.h)
            
            for y in range(self.h):
                for x in range(self.w):
                    val = self.field[y, x]
                    
                    # Fire color: czerwony (low) -> żółty (mid) -> biały (high)
                    if val < 0.4:
                        # Dark red to red
                        r = int(val * 2.5 * 180)
                        g = 0
                        b = 0
                    elif val < 0.7:
                        # Red to orange to yellow
                        r = 180
                        g = int((val - 0.4) * 3.3 * 200)
                        b = 0
                    else:
                        # Yellow to white
                        r = 180 + int((val - 0.7) * 2.5 * 75)
                        g = 200
                        b = int((val - 0.7) * 2.5 * 180)
                    
                    # Apply intensity globally
                    scale = 0.6 + 0.4 * intensity
                    r = int(min(255, r * scale))
                    g = int(min(255, g * scale))
                    b = int(min(255, b * scale))
                    
                    frame[y * self.w + x] = (r, g, b)
            
            return frame
        except Exception:
            return blank_frame(self.w, self.h)