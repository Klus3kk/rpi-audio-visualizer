import time
import numpy as np
from firmware.effects.bars import BarsEffect
from firmware.effects.wave import WaveEffect

feats = {"rms": 0.5, "bands": np.zeros(16, dtype=np.float32), "bass": 0.0, "mid": 0.0, "treble": 0.0}
bars = BarsEffect(w=16, h=16)
wave = WaveEffect(w=16, h=16)

t0 = time.time()
last = time.perf_counter()
while True:
    now = time.perf_counter()
    dt = now - last
    last = now

    t = time.time() - t0
    feats["bands"] = (np.sin(np.linspace(0, 3.14*2, 16) + t) * 0.5 + 0.5).astype(np.float32)
    feats["rms"] = float(np.mean(feats["bands"]))

    frame = bars.update(feats, dt)
    assert len(frame) == 256
    assert all(len(px) == 3 for px in frame)
    print("ok", feats["rms"])
    time.sleep(0.1)
