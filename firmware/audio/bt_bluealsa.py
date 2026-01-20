import os
import subprocess
import threading
import numpy as np
import select
import fcntl


class BlueAlsaInput:
    def __init__(self, bt_addr: str | None, rate: int = 44100, channels: int = 2, chunk_frames: int = 1024):
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

            dev = f"bluealsa:DEV={self.bt_addr},PROFILE=a2dp,SRV=org.bluealsa"
            fmt = "S16_LE"

            self._arec = subprocess.Popen(
                [
                    "arecord",
                    "-D", dev,
                    "-f", fmt,
                    "-c", str(self.channels),
                    "-r", str(self.rate),
                    "-t", "raw",
                    "-q",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,   # <= zmiana (debug)
                bufsize=0,
            )

            if self._arec.stdout is None:
                raise RuntimeError("BlueAlsaInput: arecord has no stdout")

            self._set_nonblocking(self._arec.stdout.fileno())
            if self._arec.stderr is not None:
                self._set_nonblocking(self._arec.stderr.fileno())

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

    def _drain_stderr(self, p: subprocess.Popen):
        # tylko do diagnozy: jeśli arecord się wysypuje, tu zobaczysz dlaczego
        try:
            if p.stderr is None:
                return
            fd = p.stderr.fileno()
            r, _, _ = select.select([fd], [], [], 0.0)
            if r:
                data = os.read(fd, 8192)
                if data:
                    msg = data.decode("utf-8", "ignore").strip()
                    if msg:
                        print(f"[BlueAlsaInput] arecord: {msg}", file=sys.stderr)
        except Exception:
            pass

    def read_mono_f32(self) -> np.ndarray:
        with self._lock:
            p = self._arec
            if p is None or p.stdout is None:
                return np.zeros(self.chunk_frames, dtype=np.float32)

            if p.poll() is not None:
                # spróbuj wypisać powód
                try:
                    if p.stderr is not None:
                        err = p.stderr.read().decode("utf-8", "ignore").strip()
                        if err:
                            print(f"[BlueAlsaInput] arecord exited: {err}", file=sys.stderr)
                except Exception:
                    pass
                return np.zeros(self.chunk_frames, dtype=np.float32)

            need_samples = self.chunk_frames * self.channels
            need_bytes = need_samples * 2

            fd = p.stdout.fileno()

            # mini-timeout zamiast 0.0
            try:
                r, _, _ = select.select([fd], [], [], 0.002)
                if r:
                    for _ in range(32):
                        try:
                            chunk = os.read(fd, 8192)
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
