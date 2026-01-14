import sounddevice as sd

class Passthrough:
    def __init__(self, state):
        self.state = state
        self.stream = None

    def start(self):
        d = self.state.get()
        self.stream = sd.Stream(
            samplerate=int(d.samplerate),
            blocksize=int(d.blocksize),
            dtype="float32",
            channels=1,
            device=(d.input_device, d.output_device),  # (in, out); None=default
            callback=self._cb,
        )
        self.stream.start()
        return self

    def _cb(self, indata, outdata, frames, time, status):
        d = self.state.get()
        x = indata[:, 0]
        x = x * float(d.gain)

        if d.mode == "mic" and bool(d.passthrough):
            outdata[:, 0] = x
        else:
            outdata[:, 0] = 0.0

    def close(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
