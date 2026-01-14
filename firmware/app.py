import sys
import termios
import tty
import time

from firmware.state import AppState
from firmware.audio.engine import AudioEngine
from firmware.led.engine import LedEngine
from firmware.ui.engine import UiEngine

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def main():
    state = AppState()

    audio = AudioEngine(state).start()
    leds = LedEngine(state, audio, fps=50).start()

    # jeśli LCD nie jest jeszcze gotowe, zakomentuj linię poniżej
    ui = UiEngine(state, audio, refresh_hz=5).start()

    try:
        while state.get().running:
            c = getch()

            d = state.get()
            if c == "q":
                state.update(running=False)

            elif c == "b":
                state.update(effect=("wave" if d.effect == "bars" else "bars"))

            elif c == "m":
                state.update(mode=("player" if d.mode == "analog" else "analog"))

            elif c == "+":
                state.update(brightness=min(1.0, d.brightness + 0.05))

            elif c == "-":
                state.update(brightness=max(0.05, d.brightness - 0.05))

            time.sleep(0.01)
    finally:
        state.update(running=False)
        time.sleep(0.2)

if __name__ == "__main__":
    main()
