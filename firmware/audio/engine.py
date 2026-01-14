import threading
import time
import numpy as np

from firmware.audio.capture_alsa import AlsaCapture
from firmware.audio.features import FeatureExtractor

class AudioEngine:
    def __init__(self, state):
        self.state = state
        self._lock = threading.Lock()
        self._features = {"rms": 0.0, "bands": np.zeros(16, dtype=np.float32), "bass": 0.0, "mid": 0.0, "treble": 0.0}
        self._t = None
        self._cap = None
        self._fx = None

    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def get_features(self):
        with self._lock:
            return {
                "rms": float(self._features["rms"]),
                "bands": self._features["bands"].copy(),
                "bass": float(self._features["bass"]),
                "mid": float(self._features["mid"]),
                "treble": float(self._features["treble"]),
            }

    def _run(self):
        d = self.state.get()
        self._cap = AlsaCapture(
            samplerate=d.samplerate,
            blocksize=d.blocksize,
            channels=1,
            device=d.audio_device,
        ).start()
        self._fx = FeatureExtractor(
            samplerate=d.samplerate,
            nfft=d.blocksize,
            bands=16,
        )

        try:
            while self.state.get().running:
                x = self._cap.read(timeout=1.0)
                feats = self._fx.compute(x)
                with self._lock:
                    self._features = feats
        finally:
            try:
                self._cap.close()
            except Exception:
                pass
