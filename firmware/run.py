import threading
import time
import uvicorn

from firmware.state import AppState
from firmware.audio.engine import AudioEngine
from firmware.audio.passthrough import Passthrough
from firmware.led.engine import LedEngine
from firmware.control.api import make_api
from firmware.ui.engine import UiEngine

def start_api(app, host="0.0.0.0", port=8000):
    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning")
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t

def main():
    state = AppState()

    audio = AudioEngine(state).start()
    passthrough = Passthrough(state).start()   # mic->speaker when mode==mic and passthrough==True
    leds = LedEngine(state, audio, fps=50).start()

    app = make_api(state, audio)
    start_api(app, host="0.0.0.0", port=8000)

    ui = UiEngine(state, audio, api_base="http://127.0.0.1:8000", refresh_hz=5).start()

    try:
        while state.get().running:
            time.sleep(0.2)
    finally:
        state.update(running=False)
        time.sleep(0.3)
        try:
            passthrough.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
