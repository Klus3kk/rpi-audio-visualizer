import threading
from dataclasses import dataclass

@dataclass
class AppStateData:
    mode: str = "analog"              # "analog" | "player" | "bluetooth"
    effect: str = "bars"              # nazwa efektu
    brightness: float = 0.55          # limit mocy LED 0..1

    intensity: float = 0.75           # “jak mocno wali efekt” 0..1 (wspólny knob)
    gain: float = 1.0                 # gain audio do analizy (0.2..5.0)
    smoothing: float = 0.65           # wygładzanie pasm (0..0.95)
    color_mode: str = "auto"          # "auto" | "mono" | "rainbow"

    running: bool = True
    samplerate: int = 44100
    blocksize: int = 1024
    audio_device: object = None


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
