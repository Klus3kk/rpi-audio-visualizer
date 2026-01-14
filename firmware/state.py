import threading
from dataclasses import dataclass

@dataclass
class AppStateData:
    mode: str = "analog"          # "analog" | "player"
    effect: str = "bars"          # "bars" | "wave" | ...
    brightness: float = 0.55      # 0.0..1.0 (software limit)
    running: bool = True
    samplerate: int = 44100
    blocksize: int = 1024
    audio_device: object = None   # None = default

class AppState:
    def __init__(self):
        self._lock = threading.Lock()
        self._d = AppStateData()

    def get(self) -> AppStateData:
        with self._lock:
            return AppStateData(**vars(self._d))

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._d, k):
                    setattr(self._d, k, v)
