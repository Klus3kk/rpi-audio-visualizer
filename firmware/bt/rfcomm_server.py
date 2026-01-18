# firmware/bt/rfcomm_server.py
import json
import socket
import threading
from typing import Callable, Dict, Any, Optional

class RFCOMMServer(threading.Thread):
    """
    RFCOMM JSON-line server.
    - nasłuchuje na kanale (port) RFCOMM (domyślnie 1)
    - każda linia = JSON
    - wywołuje on_message(dict)
    """
    def __init__(self, channel: int = 1, on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(daemon=True)
        self.channel = int(channel)
        self.on_message = on_message
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        # Linux BlueZ: AF_BLUETOOTH + BTPROTO_RFCOMM
        srv = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        srv.bind(("", self.channel))
        srv.listen(1)
        srv.settimeout(1.0)

        while not self._stop.is_set():
            try:
                try:
                    client, addr = srv.accept()
                except socket.timeout:
                    continue

                client.settimeout(1.0)
                buf = b""
                while not self._stop.is_set():
                    try:
                        chunk = client.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                msg = json.loads(line.decode("utf-8", errors="ignore"))
                                if isinstance(msg, dict) and self.on_message:
                                    self.on_message(msg)
                            except Exception:
                                # ignoruj śmieci
                                pass
                    except socket.timeout:
                        continue
                    except Exception:
                        break

                try:
                    client.close()
                except Exception:
                    pass
            except Exception:
                # nie ubijaj wątku, po prostu leć dalej
                continue

        try:
            srv.close()
        except Exception:
            pass
