# firmware/ui/lcd_ui.py
# Component-style LCD UI (modern-ish) with two modes:
#   - MIC: current audio input from microphone (what you have now)
#   - BT : bluetooth mode (shows BT status + connected device; audio may come from app)
#
# UI is "component" = pure state -> render(), and poll_inputs() -> actions.
# You plug it into your existing runner (test_visuals / run_with_lcd_ui).
#
# Keys:
#   LEFT/RIGHT  : prev/next effect
#   UP/DOWN     : intensity +/- 0.05
#   m           : toggle mode MIC/BT
#   c           : cycle color_mode (auto/rainbow/mono)
#   q           : quit
#
# Optional GPIO buttons supported (same as before).

import time
import math
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple

from PIL import Image, ImageDraw, ImageFont

# ---------- optional LCD backend (luma) ----------
def _try_make_luma_device(cfg: Dict[str, Any]):
    if cfg.get("backend", "luma") != "luma":
        return None
    try:
        from luma.core.interface.serial import spi
        from luma.lcd.device import st7789, ili9341
    except Exception:
        return None

    serial = spi(
        port=int(cfg.get("spi_port", 0)),
        device=int(cfg.get("spi_device", 0)),
        gpio_DC=int(cfg.get("gpio_dc", 24)),
        gpio_RST=int(cfg.get("gpio_rst", 25)),
        gpio_CS=None if cfg.get("gpio_cs", None) is None else int(cfg["gpio_cs"]),
        bus_speed_hz=int(cfg.get("spi_hz", 32000000)),
    )

    driver = str(cfg.get("driver", "st7789")).lower()
    rotate = int(cfg.get("rotate", 0))
    w = int(cfg.get("width", 240))
    h = int(cfg.get("height", 240))

    if driver == "ili9341":
        return ili9341(serial, width=w, height=h, rotate=rotate)
    return st7789(serial, width=w, height=h, rotate=rotate)


# ---------- optional GPIO buttons ----------
def _try_make_gpio_buttons(cfg: Dict[str, Any]):
    if not cfg.get("gpio_buttons", False):
        return None
    try:
        import RPi.GPIO as GPIO
    except Exception:
        return None

    GPIO.setmode(GPIO.BCM)
    pins = {
        "prev": int(cfg.get("btn_prev", 5)),
        "next": int(cfg.get("btn_next", 6)),
        "up": int(cfg.get("btn_up", 16)),
        "down": int(cfg.get("btn_down", 20)),
        "mode": int(cfg.get("btn_mode", 21)),
    }
    for p in pins.values():
        GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    return GPIO, pins


# ---------- UI state ----------
@dataclass
class BTStatus:
    enabled: bool = False
    advertising: bool = False
    connected: bool = False
    device_name: str = ""
    device_addr: str = ""
    rssi: Optional[int] = None
    last_event: str = ""  # short text

@dataclass
class UIState:
    # global
    mode: str = "MIC"  # "MIC" or "BT"
    effect_name: str = "bars"
    intensity: float = 0.75
    color_mode: str = "auto"  # auto/rainbow/mono
    fps: float = 0.0
    serial_ok: bool = True
    last_err: str = ""

    # MIC metrics
    rms: float = 0.0
    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    bands: Optional[List[float]] = None

    # BT metrics
    bt: BTStatus = field(default_factory=BTStatus)


# ---------- component ----------
class LCDUI:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self.cfg = cfg or {}
        self.device = _try_make_luma_device(self.cfg)  # may be None
        self._effects: List[str] = []
        self._effect_idx = 0

        if self.device is not None:
            self.w = int(getattr(self.device, "width", 240))
            self.h = int(getattr(self.device, "height", 240))
        else:
            self.w, self.h = 240, 240

        self.font_big = _load_font(self.cfg.get("font_big", None), 20)
        self.font_med = _load_font(self.cfg.get("font_med", None), 16)
        self.font_small = _load_font(self.cfg.get("font_small", None), 12)

        self._key_thread = _KeyboardThread()
        self._key_thread.start()

        self._gpio = None
        self._gpio_pins = None
        gb = _try_make_gpio_buttons(self.cfg)
        if gb is not None:
            self._gpio, self._gpio_pins = gb
        self._last_gpio = {"prev": 1, "next": 1, "up": 1, "down": 1, "mode": 1}

        self._blink = 0.0

    # ----- API you use in runner -----
    def set_effects(self, effect_names: List[str], current: str):
        self._effects = list(effect_names)
        self._effect_idx = self._effects.index(current) if current in self._effects else 0

    def current_effect(self) -> str:
        if not self._effects:
            return "bars"
        return self._effects[self._effect_idx % len(self._effects)]

    def poll_inputs(self) -> Dict[str, Any]:
        """
        Returns actions dict:
          {"quit": True}
          {"effect": "bars"}
          {"intensity_step": +0.05}
          {"cycle_color": True}
          {"toggle_mode": True}  # MIC <-> BT
        """
        actions: Dict[str, Any] = {}

        k = self._key_thread.pop_key()
        if k:
            if k in ("q", "Q"):
                actions["quit"] = True
                return actions
            if k == "LEFT":
                self._cycle_effect(-1); actions["effect"] = self.current_effect()
            elif k == "RIGHT":
                self._cycle_effect(+1); actions["effect"] = self.current_effect()
            elif k == "UP":
                actions["intensity_step"] = +0.05
            elif k == "DOWN":
                actions["intensity_step"] = -0.05
            elif k in ("c", "C"):
                actions["cycle_color"] = True
            elif k in ("m", "M"):
                actions["toggle_mode"] = True

        if self._gpio is not None and self._gpio_pins is not None:
            GPIO = self._gpio
            pins = self._gpio_pins

            def _edge(name: str) -> bool:
                cur = GPIO.input(pins[name])
                prev = self._last_gpio[name]
                self._last_gpio[name] = cur
                return (prev == 1 and cur == 0)

            if _edge("prev"):
                self._cycle_effect(-1); actions["effect"] = self.current_effect()
            if _edge("next"):
                self._cycle_effect(+1); actions["effect"] = self.current_effect()
            if _edge("up"):
                actions["intensity_step"] = +0.05
            if _edge("down"):
                actions["intensity_step"] = -0.05
            if _edge("mode"):
                actions["toggle_mode"] = True

        return actions

    def render(self, state: UIState):
        img = Image.new("RGB", (self.w, self.h), (0, 0, 0))
        d = ImageDraw.Draw(img)

        # top bar
        self._blink += 0.10
        dot = (math.sin(self._blink) > 0.0)
        ok = state.serial_ok
        dot_color = (0, 200, 0) if ok else ((200, 40, 40) if dot else (80, 0, 0))
        d.rectangle((0, 0, self.w, 24), fill=(10, 10, 14))
        d.ellipse((8, 7, 18, 17), fill=dot_color)

        mode_badge = state.mode
        d.text((26, 5), f"{mode_badge}", font=self.font_med, fill=(230, 230, 230))
        d.text((self.w - 74, 6), f"{state.fps:4.1f} FPS", font=self.font_small, fill=(170, 170, 170))

        # effect + controls (shared)
        d.text((10, 30), f"Effect", font=self.font_small, fill=(150, 150, 150))
        d.text((10, 44), state.effect_name, font=self.font_big, fill=(255, 255, 255))

        d.text((10, 74), f"Intensity {state.intensity:.2f}", font=self.font_small, fill=(180, 180, 180))
        _draw_bar(d, 10, 90, self.w - 20, 12, state.intensity, fill=(160, 160, 255))

        d.text((10, 108), f"Color {state.color_mode}", font=self.font_small, fill=(180, 180, 180))

        # main panel (depends on mode)
        if state.mode == "MIC":
            self._render_mic(d, state)
        else:
            self._render_bt(d, state)

        # error strip
        if state.last_err:
            d.rectangle((0, self.h - 20, self.w, self.h), fill=(20, 0, 0))
            msg = state.last_err[-44:]
            d.text((8, self.h - 18), msg, font=self.font_small, fill=(255, 120, 120))

        if self.device is not None:
            self.device.display(img)
        else:
            # console fallback
            if int(time.time()) % 1 == 0:
                if state.mode == "MIC":
                    print(f"[UI] MIC {state.effect_name} int={state.intensity:.2f} mode={state.color_mode} "
                          f"fps={state.fps:.1f} rms={state.rms:.4f}")
                else:
                    bt = state.bt
                    print(f"[UI] BT {state.effect_name} int={state.intensity:.2f} mode={state.color_mode} "
                          f"conn={bt.connected} dev={bt.device_name} rssi={bt.rssi}")

    def close(self):
        try:
            self._key_thread.stop()
        except Exception:
            pass
        if self._gpio is not None:
            try:
                self._gpio.cleanup()
            except Exception:
                pass

    # ----- internals -----
    def _cycle_effect(self, step: int):
        if not self._effects:
            return
        self._effect_idx = (self._effect_idx + step) % len(self._effects)

    def _render_mic(self, d: ImageDraw.ImageDraw, state: UIState):
        y0 = 128
        d.text((10, y0), "MIC input", font=self.font_small, fill=(150, 150, 150))
        d.text((10, y0 + 16), f"RMS  {state.rms:.4f}", font=self.font_med, fill=(230, 230, 230))
        d.text((10, y0 + 38), f"bass {state.bass:.2f}   mid {state.mid:.2f}   treb {state.treble:.2f}",
               font=self.font_small, fill=(180, 180, 180))

        if state.bands:
            _draw_mini_spectrum(d, 10, y0 + 58, self.w - 20, 44, state.bands)

    def _render_bt(self, d: ImageDraw.ImageDraw, state: UIState):
        bt = state.bt
        y0 = 128
        d.text((10, y0), "Bluetooth mode", font=self.font_small, fill=(150, 150, 150))

        # status line
        st = "CONNECTED" if bt.connected else ("ADVERTISING" if bt.advertising else ("ENABLED" if bt.enabled else "OFF"))
        st_color = (120, 220, 160) if bt.connected else (220, 200, 120) if bt.advertising else (160, 160, 160)
        d.text((10, y0 + 16), st, font=self.font_med, fill=st_color)

        # device line
        name = bt.device_name or "-"
        addr = bt.device_addr or ""
        d.text((10, y0 + 40), f"{name}", font=self.font_med, fill=(230, 230, 230))
        if addr:
            d.text((10, y0 + 60), addr, font=self.font_small, fill=(160, 160, 160))

        # RSSI + last event
        if bt.rssi is not None:
            d.text((10, y0 + 82), f"RSSI {bt.rssi} dBm", font=self.font_small, fill=(180, 180, 180))
        if bt.last_event:
            msg = bt.last_event[-34:]
            d.text((10, y0 + 100), msg, font=self.font_small, fill=(180, 180, 180))


# ---------- helpers ----------
def _load_font(path: Optional[str], size: int):
    try:
        if path:
            return ImageFont.truetype(path, size=size)
    except Exception:
        pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()

def _draw_bar(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, v: float, fill=(160, 160, 255)):
    v = 0.0 if v < 0 else (1.0 if v > 1.0 else float(v))
    d.rounded_rectangle((x, y, x + w, y + h), radius=6, outline=(70, 70, 80), width=1)
    fill_w = int(round((w - 2) * v))
    if fill_w > 0:
        d.rounded_rectangle((x + 1, y + 1, x + 1 + fill_w, y + h - 1), radius=6, fill=fill)

def _draw_mini_spectrum(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, bands: List[float]):
    n = len(bands)
    if n <= 0:
        return
    bw = max(2, w // n)
    d.rounded_rectangle((x, y, x + w, y + h), radius=10, outline=(50, 50, 60), width=1)
    for i, vv in enumerate(bands):
        vv = 0.0 if vv < 0 else (1.0 if vv > 1.0 else float(vv))
        hh = int(round(vv * (h - 6)))
        bx0 = x + 3 + i * bw
        bx1 = min(x + w - 3, bx0 + bw - 3)
        by1 = y + h - 3
        by0 = by1 - hh
        d.rectangle((bx0, by0, bx1, by1), fill=(120, 220, 160))

class _KeyboardThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop = False
        self._lock = threading.Lock()
        self._queue: List[str] = []

    def stop(self):
        self._stop = True

    def pop_key(self) -> Optional[str]:
        with self._lock:
            if not self._queue:
                return None
            return self._queue.pop(0)

    def run(self):
        try:
            import sys
            import termios
            import tty
            import select

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)

            try:
                while not self._stop:
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if not r:
                        continue
                    ch = sys.stdin.read(1)

                    key = None
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq == "[A": key = "UP"
                        elif seq == "[B": key = "DOWN"
                        elif seq == "[C": key = "RIGHT"
                        elif seq == "[D": key = "LEFT"
                    else:
                        key = ch

                    if key:
                        with self._lock:
                            self._queue.append(key)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            while not self._stop:
                time.sleep(0.2)