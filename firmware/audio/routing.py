import sounddevice as sd

def pick_input_device(prefer_substrings):
    devs = sd.query_devices()
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) <= 0:
            continue
        name = (d.get("name") or "").lower()
        ok = all(s.lower() in name for s in prefer_substrings)
        if ok:
            return i
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            return i
    return None

def input_for_mode(mode: str):
    if mode == "bt":
        return pick_input_device(["monitor", "bluez"])
    if mode == "mic":
        return pick_input_device(["usb", "mic", "quadcast", "hyperx"])
    if mode == "local":
        return pick_input_device(["monitor"])
    return pick_input_device([])
