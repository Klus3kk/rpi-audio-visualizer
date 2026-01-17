import time
from firmware.state import AppState
from firmware.audio.engine import AudioEngine
from firmware.led.engine import LedEngine

st = AppState()
st.update(
    running=True,
    mode="mic",
    input_device=0,
    output_device=0,
    effect="bars",
    brightness=0.35,
    intensity=0.85,
    gain=1.0,
    smoothing=0.65,
)

ae = AudioEngine(st).start()
le = LedEngine(st, ae, fps=30).start()

try:
    while True:
        f = ae.get_features()
        print(f"rms={f['rms']:.4f} bass={f['bass']:.2f} mid={f['mid']:.2f} treble={f['treble']:.2f}")
        time.sleep(0.2)
finally:
    st.update(running=False)
