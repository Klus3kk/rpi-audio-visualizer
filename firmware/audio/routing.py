import sounddevice as sd

# === PLACEHOLDER NAMES ===
DEFAULT_INPUT_NAMES = {
    "analog": [
        "USB", "Microphone", "Mic", "Audio", "Sound Card"
    ],
    "player": [
        "Loopback", "loopin", "ALoop", "snd-aloop"
    ],
    "bluetooth": [
        "Bluetooth", "BT", "BlueZ", "A2DP"
    ],
}

def find_device_index(mode: str):
    devices = sd.query_devices()
    needles = DEFAULT_INPUT_NAMES.get(mode, [])

    for i, d in enumerate(devices):
        name = (d.get("name") or "").lower()
        if d.get("max_input_channels", 0) <= 0:
            continue

        for needle in needles:
            if needle.lower() in name:
                return i

    # fallback: pierwszy input z kanałami
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            return i

    return None
