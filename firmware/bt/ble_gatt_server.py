# firmware/bt/ble_gatt_server.py
# BLE GATT server for Visualizer (BlueZ + D-Bus)
# JSON control via WRITE characteristic.

import json
import threading
from gi.repository import GLib
from pydbus import SystemBus

BLUEZ = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"

GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADV_IFACE = "org.bluez.LEAdvertisement1"

# D-Bus bus name MUST be like "com.something"
BUS_NAME = "com.visualizer.rpi"

SVC_UUID   = "12345678-1234-5678-1234-56789abcdef0"
CMD_UUID   = "12345678-1234-5678-1234-56789abcdef9"
STATE_UUID = "12345678-1234-5678-1234-56789abcdef8"

APP_PATH = "/com/visualizer"
SVC_PATH = APP_PATH + "/service0"
CMD_PATH = SVC_PATH + "/char0"
STATE_PATH = SVC_PATH + "/char1"
ADV_PATH = APP_PATH + "/adv0"


# ===================== SHARED STATE =====================

class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {
            "mode": "mic",
            "effect": "bars",
            "brightness": 0.55,
            "intensity": 0.75,
            "gain": 1.0,
            "smoothing": 0.65,

            # optional metadata (apka może wysyłać)
            "device_name": "",
            "device_addr": "",
            "artist": "",
            "title": "",
            "connected": False,
        }

    def update(self, patch: dict):
        with self.lock:
            for k, v in patch.items():
                if k in self.state:
                    self.state[k] = v

    def snapshot(self):
        with self.lock:
            return dict(self.state)


SHARED = SharedState()


# ===================== GATT OBJECTS =====================

class Application:
    def __init__(self):
        self.path = APP_PATH
        self.services = [Service()]

    def GetManagedObjects(self):
        objs = {}
        for s in self.services:
            objs[s.path] = s.get_props()
            for c in s.characteristics:
                objs[c.path] = c.get_props()
        return objs


class Service:
    def __init__(self):
        self.path = SVC_PATH
        self.uuid = SVC_UUID
        self.primary = True
        self.characteristics = [CmdCharacteristic(), StateCharacteristic()]

    def get_props(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": [c.path for c in self.characteristics],
            }
        }


class CmdCharacteristic:
    def __init__(self):
        self.path = CMD_PATH
        self.uuid = CMD_UUID
        self.flags = ["write", "write-without-response"]

    def WriteValue(self, value, options):
        try:
            txt = bytes(value).decode("utf-8", errors="ignore")
            patch = json.loads(txt)
            if isinstance(patch, dict):
                SHARED.update(patch)
        except Exception:
            pass

    def get_props(self):
        return {
            GATT_CHRC_IFACE: {
                "UUID": self.uuid,
                "Service": SVC_PATH,
                "Flags": self.flags,
            }
        }


class StateCharacteristic:
    def __init__(self):
        self.path = STATE_PATH
        self.uuid = STATE_UUID
        self.flags = ["read", "notify"]

    def ReadValue(self, options):
        data = json.dumps(SHARED.snapshot()).encode("utf-8")
        return list(data)

    def StartNotify(self):
        # notify jest opcjonalne; jeśli nie implementujesz push, to i tak OK
        pass

    def StopNotify(self):
        pass

    def get_props(self):
        return {
            GATT_CHRC_IFACE: {
                "UUID": self.uuid,
                "Service": SVC_PATH,
                "Flags": self.flags,
            }
        }


class Advertisement:
    def __init__(self):
        self.path = ADV_PATH
        self.props = {
            LE_ADV_IFACE: {
                "Type": "peripheral",
                "ServiceUUIDs": [SVC_UUID],
                "LocalName": "Visualizer",
                "IncludeTxPower": True,
            }
        }

    def Release(self):
        pass

    def get_props(self):
        return self.props


# ===================== SERVER START =====================

def _find_adapter(bus):
    om = bus.get(BLUEZ, "/")
    objects = om.GetManagedObjects()
    for path, ifaces in objects.items():
        if LE_ADV_MANAGER_IFACE in ifaces and GATT_MANAGER_IFACE in ifaces:
            return path
    raise RuntimeError("BLE adapter not found (no LEAdvertisingManager1/GattManager1)")


def start_ble():
    bus = SystemBus()
    adapter = _find_adapter(bus)

    app = Application()
    svc = app.services[0]
    cmd = svc.characteristics[0]
    stc = svc.characteristics[1]
    adv = Advertisement()

    # IMPORTANT: first argument is BUS_NAME, not object path
    bus.publish(
        BUS_NAME,
        (APP_PATH, app),
        (SVC_PATH, svc),
        (CMD_PATH, cmd),
        (STATE_PATH, stc),
        (ADV_PATH, adv),
    )

    gatt_mgr = bus.get(BLUEZ, adapter)
    adv_mgr = bus.get(BLUEZ, adapter)

    gatt_mgr.RegisterApplication(APP_PATH, {})
    adv_mgr.RegisterAdvertisement(ADV_PATH, {})

    GLib.MainLoop().run()
