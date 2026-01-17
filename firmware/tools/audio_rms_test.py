import time
import numpy as np
from firmware.audio.capture_alsa import AlsaCapture

cap = AlsaCapture(samplerate=44100, blocksize=1024, channels=1, device=None).start()
try:
    while True:
        x = cap.read(timeout=1.0)
        rms = float(np.sqrt(np.mean(x*x) + 1e-12))
        print(f"rms={rms:.4f}")
        time.sleep(0.05)
finally:
    cap.close()
