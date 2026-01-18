import numpy as np

def safe_bands(features, w):
    bands = np.asarray(features.get("bands", np.zeros(w)), dtype=np.float32)
    if bands.shape[0] != w:
        xi = np.linspace(0, bands.shape[0] - 1, w)
        bands = np.interp(xi, np.arange(bands.shape[0]), bands).astype(np.float32)
    if not np.isfinite(bands).all():
        bands[:] = 0.0
    return np.clip(bands, 0.0, 1.0)

def safe_rms(features):
    try:
        rms = float(features.get("rms", 0.0))
        if not np.isfinite(rms):
            return 0.0
        return rms
    except Exception:
        return 0.0

def blank_frame(w, h):
    return [(0, 0, 0)] * (w * h)
