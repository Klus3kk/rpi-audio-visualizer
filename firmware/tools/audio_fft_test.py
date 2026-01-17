import time
import numpy as np
from firmware.audio.capture_alsa import AlsaCapture
from firmware.audio.features import FeatureExtractor

DEV = 0
sr = 44100
block = 1024

cap = AlsaCapture(samplerate=sr, blocksize=block, channels=1, device=DEV).start()
fx = FeatureExtractor(samplerate=sr, nfft=block, bands=16)

try:
    while True:
        x = cap.read(timeout=1.0)
        feats = fx.compute(x, smoothing=0.65)
        bands = feats["bands"]
        print(f"rms={feats['rms']:.4f} bass={feats['bass']:.2f} mid={feats['mid']:.2f} treble={feats['treble']:.2f} top={float(np.max(bands)):.2f}")
        time.sleep(0.1)
finally:
    cap.close()
