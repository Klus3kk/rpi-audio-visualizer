# firmware/audio/sources.py
import subprocess
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd


class MicSource:
    def __init__(self, samplerate: int, blocksize: int, device: Optional[int] = None):
        self.sr = int(samplerate)
        self.bs = int(blocksize)
        self.device = device
        self.stream = sd.InputStream(
            samplerate=self.sr,
            channels=1,
            blocksize=self.bs,
            dtype="float32",
            device=self.device,
        )
        self.stream.start()

    def read(self, n: int) -> np.ndarray:
        x, _ = self.stream.read(n)
        return x[:, 0].astype(np.float32, copy=False)

    def close(self):
        try:
            self.stream.stop()
        except Exception:
            pass
        try:
            self.stream.close()
        except Exception:
            pass


class PipeWireBtSource:
    """
    Czyta audio BT przez pw-record (A2DP sink -> PipeWire).
    Uruchamia pw-record raz i czyta strumień z stdout (bez odpalania procesu co ramkę).
    """
    def __init__(self, samplerate: int, channels: int = 2, target: Optional[str] = None):
        self.sr = int(samplerate)
        self.ch = int(channels)
        self.target = target  # np. "bluez_output.xx_xx...a2dp-sink" (opcjonalne)
        self._proc = None
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._stop = False

        cmd = ["pw-record", "--format", "f32", "--rate", str(self.sr), "--channels", str(self.ch)]
        if self.target:
            cmd += ["--target", self.target]
        cmd += ["-"]  # stdout

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        if not self._proc.stdout:
            raise RuntimeError("pw-record: no stdout")

        self._thr = threading.Thread(target=self._reader, daemon=True)
        self._thr.start()

    def _reader(self):
        # zbieramy dane w buforze (lock-free na read, lock tylko na append/cut)
        while not self._stop and self._proc and self._proc.poll() is None:
            try:
                chunk = self._proc.stdout.read(4096)
                if not chunk:
                    time.sleep(0.005)
                    continue
                with self._lock:
                    self._buf += chunk
                    # limit bufora (żeby nie puchł przy lagach)
                    max_bytes = self.sr * self.ch * 4  # ~1s audio
                    if len(self._buf) > max_bytes:
                        self._buf = self._buf[-max_bytes:]
            except Exception:
                time.sleep(0.01)

    def read(self, n: int) -> np.ndarray:
        need_bytes = n * self.ch * 4
        with self._lock:
            if len(self._buf) < need_bytes:
                # za mało danych -> zwróć ciszę, nie blokuj pętli
                return np.zeros(n, dtype=np.float32)
            raw = self._buf[:need_bytes]
            del self._buf[:need_bytes]

        a = np.frombuffer(raw, dtype=np.float32)
        if a.size < n * self.ch:
            return np.zeros(n, dtype=np.float32)
        a = a.reshape(-1, self.ch)
        # mono = średnia kanałów
        return a.mean(axis=1).astype(np.float32, copy=False)

    def close(self):
        self._stop = True
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        except Exception:
            pass
        try:
            if self._proc:
                self._proc.wait(timeout=1.0)
        except Exception:
            pass
