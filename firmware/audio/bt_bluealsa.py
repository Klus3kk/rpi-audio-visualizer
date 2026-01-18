# firmware/audio/bt_bluealsa.py
# Read BT A2DP audio via BlueALSA using arecord (raw PCM).
# FIX:
# - no bluealsa-aplay here (it can steal A2DP stream from arecord)
# - non-blocking pipe read + internal buffer (never blocks caller)

import os
import subprocess
import threading
import numpy as np
import select
import fcntl


class BlueAlsaInput:
    def __init__(
        self,
        bt_addr: str | None,
        rate: int = 44100,
        channels: int = 2,
        chunk_frames: int = 1024,
    ):
        self.bt_addr = bt_addr or os.environ.get("VIS_BT_ADDR")
        self.rate = int(rate)
        self.channels = int(channels)
        self.chunk_frames = int(chunk_frames)

        self._arec: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._buf = bytearray()

    def _set_nonblocking(self, fd: int):
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def start(self):
        with self._lock:
            if self._arec is not None:
                return
            if not self.bt_addr:
                raise RuntimeError("BlueAlsaInput: bt_addr is None (set VIS_BT_ADDR or pass bt_addr)")

            dev = f"bluealsa:DEV={self.bt_addr},PROFILE=a2dp"
            fmt = "S16_LE"

            self._arec = subprocess.Popen(
                [
                    "arecord",
                    "-q",
                    "-D", dev,
                    "-f", fmt,
                    "-c", str(self.channels),
                    "-r", str(self.rate),
                    "-t", "raw",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
            if self._arec.stdout is None:
                raise RuntimeError("BlueAlsaInput: arecord has no stdout")

            self._set_nonblocking(self._arec.stdout.fileno())
            self._buf.clear()

    def stop(self):
        with self._lock:
            p = self._arec
            if p is not None:
                try:
                    p.terminate()
                except Exception:
                    pass
            self._arec = None
            self._buf.clear()

    def is_running(self) -> bool:
        with self._lock:
            return self._arec is not None and (self._arec.poll() is None)

    def read_mono_f32(self) -> np.ndarray:
        with self._lock:
            p = self._arec
            if p is None or p.stdout is None or p.poll() is not None:
                return np.zeros(self.chunk_frames, dtype=np.float32)

            need_samples = self.chunk_frames * self.channels
            need_bytes = need_samples * 2  # S16_LE

            fd = p.stdout.fileno()

            # pull what is available now (never block)
            try:
                r, _, _ = select.select([fd], [], [], 0.0)
                if r:
                    for _ in range(16):
                        try:
                            chunk = os.read(fd, 4096)
                        except BlockingIOError:
                            break
                        except Exception:
                            break
                        if not chunk:
                            break
                        self._buf.extend(chunk)
                        if len(self._buf) >= need_bytes:
                            break
            except Exception:
                return np.zeros(self.chunk_frames, dtype=np.float32)

            if len(self._buf) < need_bytes:
                return np.zeros(self.chunk_frames, dtype=np.float32)

            buf = bytes(self._buf[:need_bytes])
            del self._buf[:need_bytes]

        x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        if self.channels > 1:
            try:
                x = x.reshape(self.chunk_frames, self.channels).mean(axis=1)
            except Exception:
                return np.zeros(self.chunk_frames, dtype=np.float32)
        else:
            x = x[: self.chunk_frames]

        if not np.isfinite(x).all():
            return np.zeros(self.chunk_frames, dtype=np.float32)

        return x
