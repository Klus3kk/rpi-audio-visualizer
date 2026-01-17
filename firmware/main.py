import time
from firmware.led.esp32_serial_driver import Esp32SerialDriver
from firmware.audio.capture_alsa import AlsaCapture
from firmware.audio.features import FeatureExtractor
from firmware.effects.bars import BarsEffect

def clamp8(v):
    if v < 0: return 0
    if v > 255: return 255
    return int(v)

def apply_power_limit(frame, limit=0.55):
    if limit >= 1.0:
        return frame
    out = []
    for r, g, b in frame:
        out.append((clamp8(r * limit), clamp8(g * limit), clamp8(b * limit)))
    return out

def main():
    leds = Esp32SerialDriver(port="/dev/ttyUSB0", baud=921600, num_leds=256)

    block = 1024
    sr = 44100

    cap = AlsaCapture(samplerate=sr, blocksize=block, channels=1, device=None).start()
    fx = FeatureExtractor(samplerate=sr, nfft=block, bands=16)
    bars = BarsEffect(w=16, h=16)

    last = time.perf_counter()
    try:
        while True:
            x = cap.read(timeout=1.0)
            now = time.perf_counter()
            dt = now - last
            last = now

            features = fx.compute(x)
            frame = bars.update(features, dt)
            frame = apply_power_limit(frame, limit=0.55)

            for i, (r, g, b) in enumerate(frame):
                leds.set_pixel(i, (r, g, b))
            leds.show()
    finally:
        try:
            cap.close()
        finally:
            leds.clear()
            leds.close()

if __name__ == "__main__":
    main()
