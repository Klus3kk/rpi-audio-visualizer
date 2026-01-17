# firmware/bt/gatt_server.py
# BLE GATT server for BlueZ via D-Bus (dbus-next).
#
# Exposes:
#   Service  : 12345678-1234-5678-1234-56789abcdef0
#   CMD (W)  : 12345678-1234-5678-1234-56789abcdef9  (JSON patch from Flutter)
#   STATE (N): 12345678-1234-5678-1234-56789abcdef8  (JSON state notify to Flutter)
#
# Advertising:
#   LocalName = "Visualizer"
#   ServiceUUIDs includes the service UUID above
#
# Notes:
# - Requires BlueZ with GattManager1 + LEAdvertisingManager1.
# - Typically run as root (systemd service as root) for easiest permissions.

import asyncio
import json
from typing import Callable, Optional, Dict, Any, List

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType
from dbus_next.service import ServiceInterface, method, dbus_property, PropertyAccess
from dbus_next import Variant

BLUEZ = "org.bluez"
DBUS_OM = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP = "org.freedesktop.DBus.Properties"

GATT_MGR = "org.bluez.GattManager1"
ADV_MGR = "org.bluez.LEAdvertisingManager1"

GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
ADV_IFACE = "org.bluez.LEAdvertisement1"


def _bytes_to_str(b: bytes) -> str:
    return b.decode("utf-8", errors="ignore").strip()


def _str_to_bytes(s: str) -> bytes:
    return s.encode("utf-8")


class _Advertisement(ServiceInterface):
    def __init__(self, ad_path: str, local_name: str, service_uuids: List[str]):
        super().__init__(ADV_IFACE)
        self._path = ad_path
        self._type = "peripheral"
        self._local_name = local_name
        self._service_uuids = service_uuids

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        return self._type

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":
        return self._local_name

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":
        return self._service_uuids

    @dbus_property(access=PropertyAccess.READ)
    def Includes(self) -> "as":
        # Can include "tx-power". Keep minimal.
        return []

    @method()
    def Release(self) -> None:
        # Called by BlueZ when advertisement is released.
        return


class _Application(ServiceInterface):
    """
    ObjectManager for all services/characteristics.
    BlueZ calls GetManagedObjects() to discover the tree.
    """
    def __init__(self):
        super().__init__(DBUS_OM)
        self._objects: Dict[str, Dict[str, Dict[str, Variant]]] = {}

    def add_object(self, path: str, ifaces: Dict[str, Dict[str, Variant]]) -> None:
        self._objects[path] = ifaces

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":
        return self._objects


class _GattService(ServiceInterface):
    def __init__(self, path: str, uuid: str, primary: bool = True):
        super().__init__(GATT_SERVICE_IFACE)
        self.path = path
        self._uuid = uuid
        self._primary = primary
        self._includes: List[str] = []

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":
        return self._primary

    @dbus_property(access=PropertyAccess.READ)
    def Includes(self) -> "ao":
        return self._includes


class _CmdCharacteristic(ServiceInterface):
    """
    Write JSON patch (UTF-8). Backend callback handles validation/clamps.
    """
    def __init__(self, path: str, service_path: str, uuid: str, on_patch: Callable[[Dict[str, Any]], None]):
        super().__init__(GATT_CHRC_IFACE)
        self.path = path
        self._uuid = uuid
        self._service = service_path
        self._flags = ["write", "write-without-response"]
        self._on_patch = on_patch

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return self._service

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return self._flags

    @dbus_property(access=PropertyAccess.READ)
    def Notifying(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Value(self) -> "ay":
        return []

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        return []

    @method()
    def WriteValue(self, value: "ay", options: "a{sv}") -> None:
        try:
            raw = bytes(value)
            txt = _bytes_to_str(raw)
            if not txt:
                return
            obj = json.loads(txt)
            if isinstance(obj, dict):
                self._on_patch(obj)
        except Exception:
            # Ignore malformed writes (do not crash).
            return


class _StateCharacteristic(ServiceInterface):
    """
    Notify JSON state (UTF-8).
    """
    def __init__(self, path: str, service_path: str, uuid: str, get_state_json: Callable[[], str]):
        super().__init__(GATT_CHRC_IFACE)
        self.path = path
        self._uuid = uuid
        self._service = service_path
        self._flags = ["notify", "read"]
        self._get_state_json = get_state_json
        self._notifying = False
        s
