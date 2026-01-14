import os
import socket
import subprocess
import time
import json
from typing import Optional, Dict, Any

class MpvPlayer:
    def __init__(self, ipc_path="/tmp/mpv-ipc.sock", alsa_device="alsa/hw:Loopback,0,0"):
        self.ipc_path = ipc_path
        self.alsa_device = alsa_device
        self.proc: Optional[subprocess.Popen] = None

    def start(self):
        self.stop()

        if os.path.exists(self.ipc_path):
            try:
                os.remove(self.ipc_path)
            except Exception:
                pass

        cmd = [
            "mpv",
            "--no-video",
            f"--audio-device={self.alsa_device}",
            f"--input-ipc-server={self.ipc_path}",
            "--idle=yes",
            "--force-window=no",
            "--terminal=no",
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(80):
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

    def _send(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = (json.dumps(command) + "\n").encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.ipc_path)
            s.sendall(payload)
            data = s.recv(8192)
        try:
            return json.loads(data.decode("utf-8", errors="ignore"))
        except Exception:
            return None

    def load(self, path: str):
        return self._send({"command": ["loadfile", path, "replace"]})

    def add(self, path: str):
        return self._send({"command": ["loadfile", path, "append-play"]})

    def toggle_pause(self):
        return self._send({"command": ["cycle", "pause"]})

    def next(self):
        return self._send({"command": ["playlist-next", "force"]})

    def prev(self):
        return self._send({"command": ["playlist-prev", "force"]})

    def stop_playback(self):
        return self._send({"command": ["stop"]})

    def get_property(self, prop: str):
        return self._send({"command": ["get_property", prop]})
    
    def status(self) -> Dict[str, Any]:
        def get(prop, default=None):
            r = self.get_property(prop) or {}
            return r.get("data", default) if isinstance(r, dict) else default

        return {
            "connected": bool(get("path", "")) or bool(get("media-title", "")),
            "paused": bool(get("pause", False)),
            "path": str(get("path", "")),
            "media_title": str(get("media-title", "")),
            "time_pos": float(get("time-pos", 0.0) or 0.0),
            "duration": float(get("duration", 0.0) or 0.0),
            "percent_pos": float(get("percent-pos", 0.0) or 0.0),
            "volume": float(get("volume", 0.0) or 0.0),
        }


    def nowplaying(self) -> Dict[str, Any]:
        meta = self.get_property("metadata") or {}
        meta_val = (meta.get("data") if isinstance(meta, dict) else {}) or {}

        def pick(keys):
            for k in keys:
                if k in meta_val and meta_val[k]:
                    return str(meta_val[k])
            return ""

        st = self.status()
        title = pick(["title", "TITLE"]) or st["media_title"]
        artist = pick(["artist", "ARTIST"])
        album = pick(["album", "ALBUM"])

        return {
            "connected": st["connected"],
            "title": (title or "").strip(),
            "artist": (artist or "").strip(),
            "album": (album or "").strip(),
            "paused": st["paused"],
            "path": st["path"],
            "time_pos": st["time_pos"],
            "duration": st["duration"],
            "percent_pos": st["percent_pos"],
            "volume": st["volume"],
        }

