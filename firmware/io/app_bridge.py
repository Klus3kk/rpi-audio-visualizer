# firmware/io/app_bridge.py
import json
import socket
import threading
import time

class AppBridge:
    """
    App -> RPi bridge.
    Input: NDJSON lines (one JSON per line).
    Tries sources in order:
      1) /dev/rfcomm0 (Bluetooth SPP) if available
      2) TCP server on 127.0.0.1:8765 (fallback; app can forward via adb/ssh/tailscale/etc.)
    Exposes latest dict via .get_latest()
    """

    def __init__(self, rfcomm_dev="/dev/rfcomm0", tcp_host="127.0.0.1", tcp_port=8765):
        self.rfcomm_dev = rfcomm_dev
        self.tcp_host = tcp_host
        self.tcp_port = int(tcp_port)

        self._lock = threading.Lock()
        self._latest = {
            "connected": False,
            "device_name": "",
            "device_addr": "",
            "artist": "",
            "title": "",
            "mode": "mic",
            "effect": "",
            "intensity": None,
            "color_mode": None,
            "status": "",
        }

        self._stop = False
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def stop(self):
        self._stop = True

    def get_latest(self):
        with self._lock:
            return dict(self._latest)

    def _update(self, d):
        with self._lock:
            # merge keys we know; ignore others
            for k in list(self._latest.keys()):
                if k in d:
                    self._latest[k] = d[k]
            self._latest["_ts"] = time.monotonic()

    def _run(self):
        # Prefer rfcomm if present; otherwise TCP server.
        while not self._stop:
            try:
                import os
                if os.path.exists(self.rfcomm_dev):
                    self._read_rfcomm(self.rfcomm_dev)
                else:
                    self._serve_tcp(self.tcp_host, self.tcp_port)
            except Exception:
                time.sleep(0.5)

    def _read_rfcomm(self, dev):
        # SPP is just a serial stream; easiest: open as text.
        try:
            with open(dev, "r", buffering=1, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if self._stop:
                        return
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        if isinstance(d, dict):
                            self._update(d)
                    except Exception:
                        continue
        except Exception:
            time.sleep(0.5)

    def _serve_tcp(self, host, port):
        # Simple single-client line server; reconnects.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            s.listen(1)
            s.settimeout(1.0)

            while not self._stop:
                try:
                    conn, _addr = s.accept()
                except socket.timeout:
                    continue

                conn.settimeout(1.0)
                buf = b""
                try:
                    while not self._stop:
                        try:
                            chunk = conn.recv(4096)
                            if not chunk:
                                break
                            buf += chunk
                            while b"\n" in buf:
                                line, buf = buf.split(b"\n", 1)
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    d = json.loads(line.decode("utf-8", errors="ignore"))
                                    if isinstance(d, dict):
                                        self._update(d)
                                except Exception:
                                    continue
                        except socket.timeout:
                            continue
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
        finally:
            try:
                s.close()
            except Exception:
                pass
            time.sleep(0.5)
