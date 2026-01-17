import os, time
import numpy as np
from firmware.audio.capture_alsa import AlsaCapture

DEV = int(os.environ.get("AUDIO_DEV", "0"))

cap = AlsaCapture(samplerate=44100, blocksize=1024, channels=1, device=DEV).start()
try:
    while True:
        x = cap.read(timeout=1.0)
        rms = float(np.sqrt(np.mean(x*x) + 1e-12))
        print(f"dev={DEV} rms={rms:.5f}")
        time.sleep(0.05)
finally:
    cap.close()
