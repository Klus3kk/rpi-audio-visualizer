import threading
import time

from firmware.ui.lcd_st7789 import LcdSt7789

class UiEngine:
    def __init__(self, state, audio_engine, refresh_hz=5):
        self.state = state
        self.audio = audio_engine
        self.refresh_hz = int(refresh_hz)
        self._t = None
        self._lcd = None

    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def _run(self):
        # dopasuj piny do Twojego opisu: DC=25, RST=24, CS=5
        self._lcd = LcdSt7789(width=240, height=320, dc=25, rst=24, cs=5, rotate=0)

        while self.state.get().running:
            s = self.state.get()
            feats = self.audio.get_features()
            self._lcd.render_status(s, feats)
            time.sleep(1.0 / self.refresh_hz)
