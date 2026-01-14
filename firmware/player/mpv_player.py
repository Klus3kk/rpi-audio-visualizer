import os
import socket
import subprocess
import time
import json

class MpvPlayer:
    def __init__(self, ipc_path="/tmp/mpv-ipc.sock", alsa_device="alsa/loopout"):
        self.ipc_path = ipc_path
        self.alsa_device = alsa_device
        self.proc = None

    def start(self):
        self.stop()

        if os.path.exists(self.ipc_path):
            os.remove(self.ipc_path)

        cmd = [
            "mpv",
            "--no-video",
            f"--audio-device={self.alsa_device}",
            f"--input-ipc-server={self.ipc_path}",
            "--idle=yes",
            "--force-window=no",
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # poczekaj aż IPC wstanie
        for _ in range(50):
            if os.path.exists(self.ipc_path):
                return
            time.sleep(0.05)
        raise RuntimeError("mpv IPC did not start")

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None
        if os.path.exists(self.ipc_path):
            try:
                os.remove(self.ipc_path)
            except Exception:
                pass

    def _send(self, command):
        payload = (json.dumps(command) + "\n").encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.ipc_path)
            s.sendall(payload)
            data = s.recv(4096)
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None

    def load(self, path):
        return self._send({"command": ["loadfile", path, "replace"]})

    def toggle_pause(self):
        return self._send({"command": ["cycle", "pause"]})

    def next(self):
        return self._send({"command": ["playlist-next", "force"]})

    def prev(self):
        return self._send({"command": ["playlist-prev", "force"]})

    def set_volume(self, vol_0_100):
        v = max(0, min(100, int(vol_0_100)))
        return self._send({"command": ["set_property", "volume", v]})
