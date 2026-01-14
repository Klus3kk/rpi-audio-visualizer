import threading
import time
import uvicorn

from firmware.state import AppState
from firmware.audio.engine import AudioEngine
from firmware.led.engine import LedEngine
from firmware.control.api import make_api

# jeśli LCD gotowe i działało wcześniej, odkomentuj:
# from firmware.ui.engine import UiEngine

def start_api(app, host="0.0.0.0", port=8000):
    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning")
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t

def main():
    state = AppState()

    audio = AudioEngine(state).start()
    leds = LedEngine(state, audio, fps=50).start()

    # ui = UiEngine(state, audio, refresh_hz=5).start()

    app = make_api(state, audio)
    start_api(app, host="0.0.0.0", port=8000)

    try:
        while state.get().running:
            time.sleep(0.2)
    finally:
        state.update(running=False)
        time.sleep(0.3)

if __name__ == "__main__":
    main()
