import numpy as np
import colorsys
from firmware.effects.common import safe_bands, safe_rms, blank_frame

class VUMeterEffect:
    """
    VU meter: poziome paski (każdy wiersz = jedno pasmo).
    Pasma: 1250-20kHz (liniowo), gradient zielony -> czerwony.
    """
    def __init__(self, w=16, h=16):
        self.w = int(w)
        self.h = int(h)
        
        # Smoothing dla bardziej "analogowego" VU
        self.level = np.zeros(self.h, np.float32)
        self.attack = 0.7
        self.decay = 4.0

    def update(self, features, dt, params=None):
        try:
            dt = float(dt) if dt else 0.02
            
            # Pasma: 1250Hz do 20kHz (liniowo)
            bands = safe_bands(features, self.h)  # 16 pasm na 16 wierszy
            rms = safe_rms(features)

            if rms < 0.003:
                bands[:] = 0.0

            # Attack/decay dla każdego pasma
            target = bands * (self.w - 1)  # 0..15 pikseli szerokości
            fall = self.decay * dt

            for i in range(self.h):
                if target[i] > self.level[i]:
                    self.level[i] = (1 - self.attack) * self.level[i] + self.attack * target[i]
                else:
                    self.level[i] = max(0.0, self.level[i] - fall)

            frame = blank_frame(self.w, self.h)

            # Rysuj poziome paski (bottom = niskie freq, top = wysokie freq)
            for y in range(self.h):
                # y=0 (top) = 20kHz (czerwony), y=15 (bottom) = 1.25kHz (zielony)
                # hue: 0.33 (zielony) dla y=15, 0.0 (czerwony) dla y=0
                hue = 0.33 * (1.0 - y / max(1, self.h - 1))
                
                bar_len = int(self.level[self.h - 1 - y])  # odwróć: bottom = niskie freq
                
                for x in range(bar_len + 1):
                    # Gradient wewnątrz paska: jaśniejszy na końcu
                    brightness = 0.15 + 0.25 * (x / max(1, self.w - 1))
                    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, brightness)
                    frame[y * self.w + x] = (int(r * 255), int(g * 255), int(b * 255))

            return frame
        except Exception:
            return blank_frame(self.w, self.h)