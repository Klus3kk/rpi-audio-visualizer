# firmware/ui/lcd_ui.py
from firmware.ui.lcd_st7789 import LcdSt7789

class LCDUI:
    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self.lcd = LcdSt7789(
            width=int(self.cfg.get("width", 240)),
            height=int(self.cfg.get("height", 320)),
            spi_port=int(self.cfg.get("spi_port", 0)),
            spi_device=int(self.cfg.get("spi_device", 0)),
            dc=int(self.cfg.get("dc", 25)),
            rst=int(self.cfg.get("rst", 24)),
            cs=int(self.cfg.get("cs", 5)),
            rotate=int(self.cfg.get("rotate", 1)),  # 1 => 90deg
            spi_hz=int(self.cfg.get("spi_hz", 32_000_000)),
        )

    def close(self):
        self.lcd.dev.cleanup()

    def render(self, *, mode: str, effect: str, feats: dict, bt_connected: bool, nowp=None):
        self.lcd.render_ui(
            mode=mode,
            effect=effect,
            feats=feats,
            bt_connected=bt_connected,
            nowp=nowp,
        )
