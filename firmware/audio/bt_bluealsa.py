# firmware/audio/bt_bluealsa.py
# Read BT A2DP audio via BlueALSA using arecord (raw PCM) and optional playback via bluealsa-aplay.

import os
import subprocess
import threading
import numpy as np


class BlueAlsaInput:
    def __init__(
        self,
        bt_addr: str | None,
        rate: int = 44100,
        channels: int = 2,
        chunk_frames: int = 1024,
        playback: bool = False,
        out_pcm: str | None = None,   # e.g. "hdmi:CARD=vc4hdmi0,DEV=0"
    ):
        self.bt_addr = bt_addr or os.environ.get("VIS_BT_ADDR")  # możesz ustawić env jak chcesz
        self.rate = int(rate)
        self.channels = int(channels)
        self.chunk_frames = int(chunk_frames)
        self.playback = bool(playback)
        self.out_pcm = out_pcm

        self._arec: subprocess.Popen | None = None
        self._aplay: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._arec is not None:
                return
            if not self.bt_addr:
                raise RuntimeError("BlueAlsaInput: bt_addr is None (set VIS_BT_ADDR or pass bt_addr)")

            # CAPTURE from bluealsa via arecord
            # NOTE: quotes are handled by passing args list
            dev = f"bluealsa:DEV={self.bt_addr},PROFILE=a2dp"
            fmt = "S16_LE"

            self._arec = subprocess.Popen(
                [
                    "arecord",
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

            # Optional: PLAY to ALSA output using bluealsa-aplay (acts like "speaker")
            if self.playback:
                cmd = ["bluealsa-aplay", "--profile-a2dp"]
                if self.out_pcm:
                    cmd += ["-D", self.out_pcm]
                cmd += [self.bt_addr]
                self._aplay = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def stop(self):
        with self._lock:
            for p in (self._arec, self._aplay):
                if p is None:
                    continue
                try:
                    p.terminate()
                except Exception:
                    pass
            self._arec = None
            self._aplay = None

    def is_running(self) -> bool:
        with self._lock:
            return self._arec is not None and (self._arec.poll() is None)

    def read_mono_f32(self) -> np.ndarray:
        # returns mono float32 of length chunk_frames
        with self._lock:
            p = self._arec
            if p is None or p.stdout is None or p.poll() is not None:
                return np.zeros(self.chunk_frames, dtype=np.float32)

            need_samples = self.chunk_frames * self.channels
            need_bytes = need_samples * 2  # S16_LE

            buf = p.stdout.read(need_bytes)
            if not buf or len(buf) < need_bytes:
                return np.zeros(self.chunk_frames, dtype=np.float32)

        x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        if self.channels > 1:
            x = x.reshape(self.chunk_frames, self.channels).mean(axis=1)
        else:
            x = x[: self.chunk_frames]
        return x
