import threading
from dataclasses import dataclass

@dataclass
class AppStateData:
    # tryby: mic = mikrofon wychodzi + analiza
    # bluetooth = telefon -> Pi (A2DP sink) + analiza + LCD metadata
    # local = lokalny player (np. mpv) + analiza + LCD metadata (później)
    mode: str = "mic"                 # "mic" | "bluetooth" | "local"

    effect: str = "bars"              # bars/wave/vu/scope/radial/fire
    brightness: float = 0.55          # limit mocy LED 0..1

    intensity: float = 0.75           # 0..1 (moc efektu)
    gain: float = 1.0                 # gain wejścia do analizy / passthrough
    smoothing: float = 0.65           # 0..0.95 wygładzanie pasm
    color_mode: str = "auto"          # "auto" | "mono" | "rainbow"

    # audio routing:
    input_device: object = None       # sounddevice input index lub None=default
    output_device: object = None      # sounddevice output index lub None=default
    passthrough: bool = True          # w mic mode: czy ma “wychodzić”

    samplerate: int = 44100
    blocksize: int = 1024
    running: bool = True

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
