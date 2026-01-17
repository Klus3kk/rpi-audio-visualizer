import time
from firmware.audio.capture_alsa import AlsaCapture
from firmware.audio.features import FeatureExtractor

cap = AlsaCapture(samplerate=44100, blocksize=1024, channels=1, device=None).start()
fx = FeatureExtractor(samplerate=44100, nfft=1024, bands=16)

try:
    while True:
        x = cap.read(timeout=1.0)
        feats = fx.compute(x, smoothing=0.65)
        b = feats["bands"]
        print(f"rms={feats['rms']:.3f} bass={feats['bass']:.2f} mid={feats['mid']:.2f} treble={feats['treble']:.2f} bands[0]={b[0]:.2f} bands[15]={b[15]:.2f}")
        time.sleep(0.1)
finally:
    cap.close()
