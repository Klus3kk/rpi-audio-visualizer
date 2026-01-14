import threading
import time
import requests

from firmware.ui.lcd_st7789 import LcdSt7789

class UiEngine:
    def __init__(self, state, audio_engine, api_base="http://127.0.0.1:8000", refresh_hz=5):
        self.state = state
        self.audio = audio_engine
        self.api_base = api_base
        self.refresh_hz = int(refresh_hz)
        self._t = None
        self._lcd = None

    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def _get_nowplaying(self):
        try:
            r = requests.get(f"{self.api_base}/nowplaying", timeout=0.3)
            if r.ok:
                return r.json()
        except Exception:
            pass
        return {"source": self.state.get().mode, "connected": False, "title": "", "artist": "", "album": ""}

    def _run(self):
        self._lcd = LcdSt7789(width=240, height=320, dc=25, rst=24, cs=5, rotate=0)

        while self.state.get().running:
            s = self.state.get()
            feats = self.audio.get_features()
            nowp = self._get_nowplaying()
            self._lcd.render_status(s, feats, nowp=nowp)
            time.sleep(1.0 / self.refresh_hz)
