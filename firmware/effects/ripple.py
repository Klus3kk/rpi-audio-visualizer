import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class RippleEffect:
    """
    Concentric ripples emanating from center - beats trigger new ripples.
    Powoli zmieniający się kolor od cyan przez fiolet do magenta.
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        self.t = 0.0
        self.last_bass = 0.0
        self.ripples = []  # (birth_time, strength)
        self.color_phase = 0.0  # powolna zmiana koloru

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            self.t += dt
            
            # Powolna zmiana koloru (pełny cykl co ~20s)
            self.color_phase += dt * 0.05
            
            bands = safe_bands(features, 16)
            rms = safe_rms(features)
            bass = float(np.mean(bands[:4]))
            mid = float(np.mean(bands[4:12]))
            
            intensity = float((params or {}).get("intensity", 0.75))
            
            # Detect bass hits (trigger new ripples)
            if bass > self.last_bass + 0.12 and bass > 0.25:
                self.ripples.append((self.t, bass))
            self.last_bass = bass * 0.85 + self.last_bass * 0.15
            
            # Remove old ripples
            self.ripples = [(t, s) for (t, s) in self.ripples if self.t - t < 2.5]

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
                        ripple_r = age * 9.0  # szybsza fala
                        
                        # Distance from ripple ring
                        dist = abs(r - ripple_r)
                        
                        if dist < 2.5:
                            # Gaussian falloff
                            wave = np.exp(-dist * dist / 0.6)
                            fade = max(0.0, 1.0 - age / 2.5)
                            val += wave * fade * strength
                    
                    val = min(1.0, val) * intensity
                    
                    if val > 0.05:
                        # Powolna zmiana: cyan (0.5) -> fiolet (0.75) -> magenta (0.85) -> cyan
                        base_hue = 0.5 + 0.35 * np.sin(self.color_phase)
                        
                        # Lekki shift od mid frequencies
                        hue = (base_hue + mid * 0.1) % 1.0
                        sat = 0.9
                        
                        # Ciemniej
                        brightness = val * 0.3
                        
                        r_c, g_c, b_c = colorsys.hsv_to_rgb(hue, sat, brightness)
                        frame[y * self.w + x] = (int(r_c * 255), int(g_c * 255), int(b_c * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)