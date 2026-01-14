import threading
import time
import numpy as np

from firmware.audio.capture_alsa import AlsaCapture
from firmware.audio.features import FeatureExtractor

class AudioEngine:
    def __init__(self, state):
        self.state = state
        self._lock = threading.Lock()
        self._features = {
            "rms": 0.0,
            "bands": np.zeros(16, dtype=np.float32),
            "bass": 0.0,
            "mid": 0.0,
            "treble": 0.0,
        }
        self._t = None
        self._cap = None
        self._fx = None
        self._cfg_sig = None

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

    def _make_cfg_sig(self, d):
        # signature: jeśli się zmieni, restartujemy stream
        return (d.samplerate, d.blocksize, d.audio_device)

    def _start_stream(self, d):
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
        self._cfg_sig = self._make_cfg_sig(d)

    def _stop_stream(self):
        try:
            if self._cap is not None:
                self._cap.close()
        except Exception:
            pass
        self._cap = None
        self._fx = None

    def _run(self):
        try:
            self._start_stream(self.state.get())

            while self.state.get().running:
                d = self.state.get()
                sig = self._make_cfg_sig(d)
                if sig != self._cfg_sig:
                    self._stop_stream()
                    time.sleep(0.1)
                    self._start_stream(d)

                x = self._cap.read(timeout=1.0)
                d = self.state.get()
                x = x * float(d.gain)
                feats = self._fx.compute(x, smoothing=float(d.smoothing))


                with self._lock:
                    self._features = feats
        finally:
            self._stop_stream()
