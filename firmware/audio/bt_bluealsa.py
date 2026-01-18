# firmware/audio/bt_bluealsa.py
import os
import re
import subprocess
import threading
from typing import Optional

import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None


def _run_cmd_lines(cmd) -> str:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        return p.stdout or ""
    except Exception:
        return ""


def detect_bluealsa_dev_addr(prefer_addr: Optional[str] = None) -> Optional[str]:
    env_addr = os.environ.get("VIS_BT_ADDR", "").strip()
    if env_addr:
        return env_addr
    if prefer_addr:
        return prefer_addr

    out = _run_cmd_lines(["bluealsa-aplay", "-L"])
    m = re.search(r"DEV=([0-9A-Fa-f:]{17})", out)
    if m:
        return m.group(1).upper()
    return None


class BlueAlsaInput:
    """
    BT A2DP capture via BlueALSA:
      arecord -D bluealsa:DEV=..,PROFILE=a2dp -f S16_LE -c2 -r44100 -t raw

    Optionally plays audio to local speakers using sounddevice OutputStream.
    """

    def __init__(
        self,
        *,
        bt_addr: Optional[str] = None,
        rate: int = 44100,
        channels: int = 2,
        chunk_frames: int = 1024,
        playback: bool = True,
        out_device: Optional[int] = None,
    ):
        self.rate = int(rate)
        self.channels = int(channels)
        self.chunk_frames = int(chunk_frames)
        self.playback = bool(playback and sd is not None)
        self.out_device = out_device

        self.bt_addr = detect_bluealsa_dev_addr(bt_addr)
        self._proc: Optional[subprocess.Popen] = None
        self._out = None
        self._lock = threading.Lock()
        self._alive = False

    def start(self):
        if not self.bt_addr:
            raise RuntimeError("BlueALSA: no BT address detected. Set VIS_BT_ADDR or pass bt_addr.")

        dev = f"bluealsa:DEV={self.bt_addr},PROFILE=a2dp"
        cmd = [
            "arecord",
            "-D", dev,
            "-f", "S16_LE",
            "-c", str(self.channels),
            "-r", str(self.rate),
            "-t", "raw",
        ]

        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        if not self._proc.stdout:
            raise RuntimeError("BlueALSA: arecord stdout missing")

        if self.playback:
            self._out = sd.OutputStream(
                samplerate=self.rate,
                channels=self.channels,
                dtype="float32",
                device=self.out_device,
                blocksize=self.chunk_frames,
            )
            self._out.start()

        with self._lock:
            self._alive = True

    def stop(self):
        with self._lock:
            self._alive = False

        try:
            if self._out is not None:
                self._out.stop()
                self._out.close()
        except Exception:
            pass
        self._out = None

        try:
            if self._proc is not None:
                self._proc.terminate()
        except Exception:
            pass

        try:
            if self._proc is not None:
                self._proc.wait(timeout=1.0)
        except Exception:
            pass

        self._proc = None

    def is_running(self) -> bool:
        with self._lock:
            return self._alive

    def read_mono_f32(self) -> np.ndarray:
        with self._lock:
            ok = self._alive and (self._proc is not None) and (self._proc.stdout is not None)
        if not ok:
            return np.zeros(self.chunk_frames, dtype=np.float32)

        bytes_per_frame = 2 * self.channels  # S16_LE
        need = self.chunk_frames * bytes_per_frame

        raw = self._proc.stdout.read(need)  # type: ignore[union-attr]
        if not raw or len(raw) < need:
            return np.zeros(self.chunk_frames, dtype=np.float32)

        a = np.frombuffer(raw, dtype=np.int16).reshape(-1, self.channels)
        stereo = a.astype(np.float32) / 32768.0

        # playback to speakers
        if self._out is not None:
            try:
                self._out.write(stereo)
            except Exception:
                pass

        mono = np.mean(stereo, axis=1)
        return mono.astype(np.float32, copy=False)
