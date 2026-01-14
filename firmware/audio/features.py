import numpy as np

def _hz_to_bin(freq_hz, nfft, sr):
    return int(np.floor((freq_hz / (sr / 2.0)) * (nfft // 2)))

class FeatureExtractor:
    def __init__(self, samplerate=44100, nfft=1024, bands=16, fmin=40, fmax=16000):
        self.sr = int(samplerate)
        self.nfft = int(nfft)
        self.bands = int(bands)
        self.fmin = float(fmin)
        self.fmax = float(fmax)

        self.window = np.hanning(self.nfft).astype(np.float32)
        self.prev_bands = np.zeros(self.bands, dtype=np.float32)

        edges_hz = np.geomspace(self.fmin, self.fmax, num=self.bands + 1)
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

        rms = float(np.sqrt(np.mean(x * x) + 1e-12))

        xw = x * self.window
        spec = np.fft.rfft(xw)
        mag = np.abs(spec).astype(np.float32)
        mag[0] = 0.0

        band_vals = np.zeros(self.bands, dtype=np.float32)
        for i, (lo, hi) in enumerate(self.edges):
            band_vals[i] = np.mean(mag[lo:hi]) if hi > lo else 0.0

        band_vals = np.log1p(band_vals)

        band_vals = (smoothing * self.prev_bands) + ((1.0 - smoothing) * band_vals)
        self.prev_bands = band_vals

        bmin = float(np.min(band_vals))
        bmax = float(np.max(band_vals))
        if bmax - bmin < 1e-6:
            bands_norm = np.zeros_like(band_vals)
        else:
            bands_norm = (band_vals - bmin) / (bmax - bmin)

        bass = float(np.mean(bands_norm[: max(1, self.bands // 6)]))
        mid = float(np.mean(bands_norm[self.bands // 6 : 4 * self.bands // 6]))
        treble = float(np.mean(bands_norm[4 * self.bands // 6 :]))

        return {
            "rms": rms,
            "bands": bands_norm,
            "bass": bass,
            "mid": mid,
            "treble": treble,
        }
