# firmware/visualizer_core.py
#
# Single-process backend:
# - AudioEngine (MIC or BT based on sounddevice input_device)
# - LedEngine (effects + ESP32 serial frames)
# - Passthrough (optional) for mic->speaker
# - BLE GATT server (CMD write JSON patch, STATE notify JSON)
#
# Run under systemd as root for simplest BlueZ D-Bus permissions.

import asyncio
import json
from typing import Dict, Any

from firmware.state import AppState
from firmware.audio.engine import AudioEngine
from firmware.audio.passthrough import Passthrough
from firmware.audio.routing import input_for_mode
from firmware.led.engine import LedEngine

from firmware.bt.gatt_server import BleGattServer

DEVICE_NAME = "Visualizer"

SVC_UUID = "12345678-1234-5678-1234-56789abcdef0"
CMD_UUID = "12345678-1234-5678-1234-56789abcdef9"
STATE_UUID = "12345678-1234-5678-1234-56789abcdef8"


def _clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _mode_in_to_internal(m: str) -> str:
    # Flutter sends "bt"; your state currently uses "bluetooth"
    if m == "bt":
        return "bluetooth"
    return m


def _mode_internal_to_out(m: str) -> str:
    if m == "bluetooth":
        return "bt"
    return m


def make_snapshot(state: AppState) -> Dict[str, Any]:
    s = state.get()
    return {
        "mode": _mode_internal_to_out(str(s.mode)),
        "effect": str(s.effect),
        "brightness": float(s.brightness),
        "intensity": float(s.intensity),
        "gain": float(s.gain),
        "smoothing": float(s.smoothing),
        # optional extras (safe for Flutter: it ignores unknown keys)
        "color_mode": str(s.color_mode),
    }


def snapshot_json(state: AppState) -> str:
    return json.dumps(make_snapshot(state), separators=(",", ":"))


def apply_patch(state: AppState, patch: Dict[str, Any]) -> None:
    """
    Mirrors your FastAPI PATCH /state logic, but for BLE.
    """
    upd: Dict[str, Any] = {}

    # mode
    if "mode" in patch and patch["mode"] is not None:
        raw = str(patch["mode"])
        m = _mode_in_to_internal(raw)
        if m in ("mic", "bluetooth", "local"):
            upd["mode"] = m
            # auto input device selection
            auto_in = input_for_mode(m)
            if auto_in is not None:
                upd["input_device"] = auto_in

    # effect
    if "effect" in patch and patch["effect"] is not None:
        upd["effect"] = str(patch["effect"])

    # brightness/intensity/gain/smoothing
    if "brightness" in patch and patch["brightness"] is not None:
        upd["brightness"] = _clamp(float(patch["brightness"]), 0.0, 1.0)

    if "intensity" in patch and patch["intensity"] is not None:
        upd["intensity"] = _clamp(float(patch["intensity"]), 0.0, 1.0)

    if "gain" in patch and patch["gain"] is not None:
        upd["gain"] = _clamp(float(patch["gain"]), 0.1, 6.0)

    if "smoothing" in patch and patch["smoothing"] is not None:
        upd["smoothing"] = _clamp(float(patch["smoothing"]), 0.0, 0.95)

    # optional: color_mode
    if "color_mode" in patch and patch["color_mode"] is not None:
        upd["color_mode"] = str(patch["color_mode"])

    if upd:
        state.update(**upd)


async def main() -> None:
    state = AppState()

    audio = AudioEngine(state).start()
    passthrough = Passthrough(state).start()
    leds = LedEngine(state, audio, fps=15).start()  # 115200 baud => ~15 FPS practical

    # BLE server
    ble: BleGattServer

    def on_patch(p: Dict[str, Any]) -> None:
        apply_patch(state, p)
        # push state after every patch
        ble.notify_state()

    def get_state_json() -> str:
        return snapshot_json(state)

    ble = BleGattServer(
        device_name=DEVICE_NAME,
        service_uuid=SVC_UUID,
        cmd_uuid=CMD_UUID,
        state_uuid=STATE_UUID,
        on_patch=on_patch,
        get_state_json=get_state_json,
        adapter="hci0",
        base_path="/org/visualizer",
    )

    await ble.start()
    ble.notify_state()  # initial push if notify is enabled on client

    try:
        while state.get().running:
            # periodic notify (optional): keeps app UI synced even if state changes elsewhere
            ble.notify_state()
            await asyncio.sleep(0.5)
    finally:
        state.update(running=False)
        try:
            passthrough.close()
        except Exception:
            pass
        try:
            await ble.stop()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
