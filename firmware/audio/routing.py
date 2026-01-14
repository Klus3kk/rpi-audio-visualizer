import sounddevice as sd

def pick_input_device(prefer_substrings):
    devs = sd.query_devices()
    # 1) preferowane po nazwie
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) <= 0:
            continue
        name = (d.get("name") or "").lower()
        for s in prefer_substrings:
            if s.lower() in name:
                return i
    # 2) fallback: pierwszy input z kanałami
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            return i
    return None

def input_for_mode(mode: str):
    if mode == "bluetooth":
        # loopback capture (snd-aloop) – to jest nasz “tap”
        return pick_input_device(["loopback", "aloop", "snd_aloop"])
    if mode == "mic":
        # USB mic – best-effort
        return pick_input_device(["usb", "microphone", "mic"])
    if mode == "local":
        return pick_input_device(["loopback", "aloop", "snd_aloop"])

    return pick_input_device([])
