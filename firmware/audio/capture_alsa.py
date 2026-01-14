import queue
import sounddevice as sd
import numpy as np

class AlsaCapture:
    def __init__(self, samplerate=44100, blocksize=1024, channels=1, device=None):
        self.samplerate = int(samplerate)
        self.blocksize = int(blocksize)
        self.channels = int(channels)
        self.device = device
        self.q = queue.Queue(maxsize=8)
        self.stream = None

    @staticmethod
    def list_devices():
        return sd.query_devices()

    def _callback(self, indata, frames, time, status):
        if status:
            pass
        x = indata.copy()
        try:
            self.q.put_nowait(x)
        except queue.Full:
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            try:
                self.q.put_nowait(x)
            except queue.Full:
                pass

    def start(self):
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=self.channels,
            device=self.device,
            dtype="float32",
            callback=self._callback,
        )
        self.stream.start()
        return self

    def read(self, timeout=1.0):
        x = self.q.get(timeout=timeout)  # shape: (blocksize, channels)
        if self.channels > 1:
            x = np.mean(x, axis=1, keepdims=True)
        return x[:, 0]

    def close(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
