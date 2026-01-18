# firmware/bt/ble_gatt_server.py
# BLE GATT server for Visualizer (BlueZ + D-Bus)
# Any device can connect. JSON control via WRITE characteristic.

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

SVC_UUID   = "12345678-1234-5678-1234-56789abcdef0"
CMD_UUID   = "12345678-1234-5678-1234-56789abcdef9"
STATE_UUID = "12345678-1234-5678-1234-56789abcdef8"

APP_PATH = "/visualizer"
SVC_PATH = APP_PATH + "/service0"
CMD_PATH = SVC_PATH + "/char0"
STATE_PATH = SVC_PATH + "/char1"
ADV_PATH = "/visualizer/adv0"


# ===================== SHARED STATE =====================

class SharedState:
    """
    Shared state between BLE and main loop.

    NOTE:
    - accept patches for known keys only (prevents junk)
    - includes BT metadata fields for LCD display in BT mode
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {
            # control
            "mode": "mic",            # mic|bt
            "effect": "bars",
            "brightness": 0.55,
            "intensity": 0.75,
            "gain": 1.0,
            "smoothing": 0.65,
            "color_mode": "auto",     # auto|rainbow|mono  (jeśli apka zacznie wysyłać)

            # bt metadata (for LCD)
            "connected": False,
            "device_name": "",
            "device_addr": "",
            "artist": "",
            "title": "",
        }

        # whitelist
        self.allowed = set(self.state.keys())

    def update(self, patch: dict):
        with self.lock:
            for k, v in patch.items():
                if k not in self.allowed:
                    continue
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

    def get_path(self):
        return self.path

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
            txt = bytes(value).decode("utf-8")
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
    """
    Optional notify characteristic. Your app already supports it (kState).
    We implement Notify via PropertiesChanged on org.freedesktop.DBus.Properties.
    """
    def __init__(self):
        self.path = STATE_PATH
        self.uuid = STATE_UUID
        self.flags = ["notify", "read"]
        self._notifying = False
        self._bus = None
        self._last_json = ""

    def _emit_changed(self):
        if not self._notifying or self._bus is None:
            return
        try:
            # properties changed signal
            props_iface = "org.freedesktop.DBus.Properties"
            chrc_iface = GATT_CHRC_IFACE
            val = list(json.dumps(SHARED.snapshot()).encode("utf-8"))
            self._bus.con.signal(
                self.path,
                props_iface,
                "PropertiesChanged",
                "sa{sv}as",
                (chrc_iface, {"Value": val}, []),
            )
        except Exception:
            pass

    def ReadValue(self, options):
        data = json.dumps(SHARED.snapshot()).encode("utf-8")
        return list(data)

    def StartNotify(self):
        self._notifying = True
        # start periodic notify every 500ms (lightweight)
        def tick():
            if not self._notifying:
                return False
            snap = SHARED.snapshot()
            js = json.dumps(snap, separators=(",", ":"))
            if js != self._last_json:
                self._last_json = js
                self._emit_changed()
            return True
        GLib.timeout_add(500, tick)

    def StopNotify(self):
        self._notifying = False

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

    def get_path(self):
        return self.path

    def get_props(self):
        return self.props

    def Release(self):
        pass


# ===================== SERVER START =====================

def _find_adapter(bus):
    om = bus.get(BLUEZ, "/")
    objects = om.GetManagedObjects()
    for path, ifaces in objects.items():
        if LE_ADV_MANAGER_IFACE in ifaces and GATT_MANAGER_IFACE in ifaces:
            return path
    raise RuntimeError("BLE adapter not found")


def start_ble():
    bus = SystemBus()
    adapter = _find_adapter(bus)

    app = Application()
    adv = Advertisement()

    # publish objects
    bus.publish(APP_PATH, app)
    bus.publish(SVC_PATH, app.services[0])
    for c in app.services[0].characteristics:
        # attach bus for notify characteristic
        if isinstance(c, StateCharacteristic):
            c._bus = bus
        bus.publish(c.path, c)
    bus.publish(ADV_PATH, adv)

    gatt_mgr = bus.get(BLUEZ, adapter)
    adv_mgr = bus.get(BLUEZ, adapter)

    gatt_mgr.RegisterApplication(APP_PATH, {})
    adv_mgr.RegisterAdvertisement(ADV_PATH, {})

    loop = GLib.MainLoop()
    loop.run()
