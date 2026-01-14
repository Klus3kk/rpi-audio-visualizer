import json
import subprocess
import time
import signal
import sys
from typing import Optional, Tuple

TAG = "BT->ALOOP tap"

def sh(cmd):
    return subprocess.check_output(cmd, text=True)

def pw_dump():
    return json.loads(sh(["pw-dump"]))

def find_targets(dump) -> Tuple[Optional[int], Optional[int]]:
    """
    Zwraca: (bt_sink_node_id, aloop_playback_node_id)
    Heurystyki:
    - BT sink: node.name zawiera 'bluez_output' albo opis zawiera 'Bluetooth'
    - ALOOP playback: node.name zawiera 'snd_aloop' lub opis zawiera 'Loopback' i jest alsa_output
    """
    bt_id = None
    aloop_id = None

    for obj in dump:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        info = obj.get("info", {})
        props = info.get("props", {}) or {}
        node_id = obj.get("id")

        name = (props.get("node.name") or "").lower()
        desc = (props.get("node.description") or "").lower()
        media_class = (props.get("media.class") or "").lower()

        # BT node: najczęściej 'bluez_output.<mac>.a2dp-sink'
        if bt_id is None and "audio/sink" in media_class:
            if "bluez_output" in name or "bluetooth" in desc:
                bt_id = node_id

        # ALSA loopback playback node: często zawiera snd_aloop
        if aloop_id is None and "audio/sink" in media_class:
            if "snd_aloop" in name or ("loopback" in desc and "alsa_output" in name):
                aloop_id = node_id

    return bt_id, aloop_id

def start_pw_loopback(bt_id: int, aloop_id: int) -> subprocess.Popen:
    cmd = [
        "pw-loopback",
        f"--capture-props=node.target={bt_id},node.description={TAG}",
        f"--playback-props=node.target={aloop_id},node.description={TAG}",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    proc = None
    last = (None, None)

    def cleanup(*_):
        nonlocal proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    while True:
        try:
            dump = pw_dump()
            bt_id, aloop_id = find_targets(dump)

            targets = (bt_id, aloop_id)

            if bt_id is None or aloop_id is None:
                # nie ma BT lub nie ma aloop -> zatrzymaj loopback
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc = None
                last = targets
                time.sleep(2.0)
                continue

            # zmiana targetów lub proces padł -> restart
            need_restart = (targets != last) or (proc is None) or (proc.poll() is not None)
            if need_restart:
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc = None
                proc = start_pw_loopback(bt_id, aloop_id)
                last = targets

        except Exception:
            # w razie błędu: nie spamuj, spróbuj za chwilę
            time.sleep(2.0)

        time.sleep(1.0)

if __name__ == "__main__":
    main()
