# firmware/bt/ble_gatt_server.py
# BlueZ GATT server (DBus) - Visualizer
# JSON control via WRITE characteristic + STATE readable.
#
# Requires: python3-dbus, python3-gi
#
# Run note: registering advertisement often requires root or proper polkit rules.
# If it fails, run your main script with: sudo -E python3 -u -m firmware.tools.run_with_lcd_ui

import json
import threading
import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service

from gi.repository import GLib

BLUEZ_SERVICE_NAME = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"

GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADV_IFACE = "org.bluez.LEAdvertisement1"

# UUIDs
SVC_UUID = "12345678-1234-5678-1234-56789abcdef0"
CMD_UUID = "12345678-1234-5678-1234-56789abcdef9"   # WRITE
STATE_UUID = "12345678-1234-5678-1234-56789abcdef8" # READ/NOTIFY(optional)

# Paths
APP_PATH = "/com/visualizer/app"
ADV_PATH = "/com/visualizer/adv"


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
            "color_mode": "auto",

            # optional metadata (apka może wysyłać)
            "device_name": "",
            "device_addr": "",
            "artist": "",
            "title": "",
            "album": "",
            "cover_url": "",
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


# ===================== HELPERS =====================

def _find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
    objects = om.GetManagedObjects()
    for path, ifaces in objects.items():
        if LE_ADV_MANAGER_IFACE in ifaces and GATT_MANAGER_IFACE in ifaces:
            return path
    raise RuntimeError("No BLE adapter with LEAdvertisingManager1 + GattManager1 found")


def _to_dbus_array_of_bytes(b: bytes):
    return dbus.Array([dbus.Byte(x) for x in b], signature="y")


# ===================== DBUS BASE CLASSES =====================

class Application(dbus.service.Object):
    """
    org.freedesktop.DBus.ObjectManager
    """
    def __init__(self, bus):
        self.path = APP_PATH
        self.bus = bus
        self.services = []
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.characteristics:
                response[chrc.get_path()] = chrc.get_properties()
        return response



class Service(dbus.service.Object):
    """
    org.bluez.GattService1
    """
    def __init__(self, bus, index, uuid, primary=True):
        self.bus = bus
        self.path = APP_PATH + f"/service{index}"
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        super().__init__(bus, self.path)

    def add_characteristic(self, chrc):
        self.characteristics.append(chrc)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [c.get_path() for c in self.characteristics],
                    signature="o",
                ),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException("org.bluez.Error.InvalidArgs", "Wrong interface")
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    """
    org.bluez.GattCharacteristic1
    """
    def __init__(self, bus, index, uuid, flags, service):
        self.bus = bus
        self.path = service.path + f"/char{index}"
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self.notifying = False
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": dbus.Array(self.flags, signature="s"),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException("org.bluez.Error.InvalidArgs", "Wrong interface")
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        raise dbus.exceptions.DBusException("org.bluez.Error.NotPermitted", "Read not permitted")

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        raise dbus.exceptions.DBusException("org.bluez.Error.NotPermitted", "Write not permitted")

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False


class Advertisement(dbus.service.Object):
    """
    org.bluez.LEAdvertisement1
    """
    def __init__(self, bus, index, ad_type="peripheral"):
        self.bus = bus
        self.path = ADV_PATH + str(index)
        self.ad_type = ad_type
        self.service_uuids = [SVC_UUID]
        self.local_name = "Visualizer"
        self.include_tx_power = True
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        props = {
            "Type": self.ad_type,
            "ServiceUUIDs": dbus.Array(self.service_uuids, signature="s"),
            "LocalName": dbus.String(self.local_name),
        }
        if self.include_tx_power:
            props["IncludeTxPower"] = dbus.Boolean(True)
        return {LE_ADV_IFACE: props}

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADV_IFACE:
            raise dbus.exceptions.DBusException("org.bluez.Error.InvalidArgs", "Wrong interface")
        return self.get_properties()[LE_ADV_IFACE]

    @dbus.service.method(LE_ADV_IFACE)
    def Release(self):
        pass


# ===================== YOUR CHARACTERISTICS =====================

class CmdCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, CMD_UUID, ["write", "write-without-response"], service)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        try:
            b = bytes(value)
            txt = b.decode("utf-8", errors="ignore")
            patch = json.loads(txt)
            if isinstance(patch, dict):
                SHARED.update(patch)
        except Exception:
            pass


class StateCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        # notify jest opcjonalne; bez push i tak OK (read działa)
        super().__init__(bus, index, STATE_UUID, ["read", "notify"], service)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        data = json.dumps(SHARED.snapshot()).encode("utf-8")
        return _to_dbus_array_of_bytes(data)


class VisualizerService(Service):
    def __init__(self, bus, index=0):
        super().__init__(bus, index, SVC_UUID, primary=True)
        self.add_characteristic(CmdCharacteristic(bus, 0, self))
        self.add_characteristic(StateCharacteristic(bus, 1, self))


# ===================== SERVER START =====================

def start_ble():
    """
    Starts BLE GATT + Advertisement.
    If you get permission errors, run the whole app with sudo.
    """
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter_path = _find_adapter(bus)

    app = Application(bus)
    app.add_service(VisualizerService(bus, 0))

    service_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), GATT_MANAGER_IFACE)
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), LE_ADV_MANAGER_IFACE)

    adv = Advertisement(bus, 0, ad_type="peripheral")

    # Register
    service_manager.RegisterApplication(app.get_path(), {},
                                        reply_handler=lambda: None,
                                        error_handler=lambda e: print("GATT register failed:", e))

    ad_manager.RegisterAdvertisement(adv.get_path(), {},
                                     reply_handler=lambda: None,
                                     error_handler=lambda e: print("ADV register failed:", e))

    GLib.MainLoop().run()
