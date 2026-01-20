import numpy as np

def _hz_to_bin(freq_hz, nfft, sr):
    return int(np.floor((freq_hz / (sr / 2.0)) * (nfft // 2)))

class FeatureExtractor:
    def __init__(self, samplerate=44100, nfft=1024, bands=16, fmin=1250, fmax=20000):
        self.sr = int(samplerate)
        self.nfft = int(nfft)
        self.bands = int(bands)
        self.fmin = float(fmin)
        self.fmax = float(fmax)

        self.window = np.hanning(self.nfft).astype(np.float32)
        self.prev_bands = np.zeros(self.bands, dtype=np.float32)

        # LINEAR spacing: 1250Hz do 20kHz = 18750 Hz / 16 pasm = ~1172 Hz na pasmo
        edges_hz = np.linspace(self.fmin, self.fmax, num=self.bands + 1)
        self.edges = []
        for i in range(self.bands):
            lo = max(1, _hz_to_bin(edges_hz[i], self.nfft, self.sr))
            hi = max(lo + 1, _hz_to_bin(edges_hz[i + 1], self.nfft, self.sr))
            self.edges.append((lo, hi))

    def compute(self, x, smoothing=0.65):
        x = x[: self.nfft].astype(np.float32, copy=False)
        if x.shape[0] < self.nfft:
            pad = np.zeros(self.nfft, dtype=np.float32)
            pad[: x.shape[0]] = x
            x = pad

        # RMS do gate (cisza)
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))

        xw = x * self.window
        spec = np.fft.rfft(xw)
        mag2 = (spec.real * spec.real + spec.imag * spec.imag).astype(np.float32)
        mag2[0] = 0.0  # usuń DC

        band_vals = np.zeros(self.bands, dtype=np.float32)
        for i, (lo, hi) in enumerate(self.edges):
            if hi > lo:
                band_vals[i] = float(np.mean(mag2[lo:hi]))
            else:
                band_vals[i] = 0.0

        # dB scale (stabilniejsze niż log1p)
        band_db = 10.0 * np.log10(band_vals + 1e-12).astype(np.float32)

        # smoothing w dB (żeby nie pompowało)
        band_db = (smoothing * self.prev_bands) + ((1.0 - smoothing) * band_db)
        self.prev_bands = band_db

        # Adaptacyjna skala zależna od źródła (parametr opcjonalny)
        # Spotify/BT: -14 LUFS (głośniejsze), Mic: -30 LUFS (cichsze)
        # Możemy to wykryć po RMS, ale na razie STAŁA skala uniwersalna:
        NOISE_FLOOR_DB = -80.0   # niżej = więcej czułości na ciche dźwięki
        RANGE_DB = 50.0          # zakres dynamiczny
        RMS_GATE = 0.004         # próg ciszy (niżej niż wcześniej)

        # mapowanie do 0..1
        bands_norm = (band_db - NOISE_FLOOR_DB) / RANGE_DB
        bands_norm = np.clip(bands_norm, 0.0, 1.0)
        
        if rms < RMS_GATE:
            bands_norm[:] = 0.0

        # bass/mid/treble - teraz wszystkie pasma są w zakresie 1.25-20kHz
        # więc bass = dolne 1/3, mid = środkowe 1/3, treble = górne 1/3
        third = max(1, self.bands // 3)
        bass = float(np.mean(bands_norm[:third]))
        mid = float(np.mean(bands_norm[third:2*third]))
        treble = float(np.mean(bands_norm[2*third:]))

        return {
            "rms": rms,
            "bands": bands_norm,
            "bass": bass,
            "mid": mid,
            "treble": treble,
            "samplerate": self.sr,
            "nfft": self.nfft,
            "mag": mag2,
        }