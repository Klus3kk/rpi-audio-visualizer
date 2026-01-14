import asyncio
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

BLUEZ = "org.bluez"
MP_IFACE = "org.bluez.MediaPlayer1"
PROP_IFACE = "org.freedesktop.DBus.Properties"
OBJMGR_IFACE = "org.freedesktop.DBus.ObjectManager"

class BtMetadata:
    def __init__(self):
        self.track = {"Title": "", "Artist": "", "Album": "", "Duration": 0}
        self.connected = False
        self._bus = None
        self._props = None
        self._player_path = None

    async def start(self):
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        intro = await self._bus.introspect(BLUEZ, "/")
        root_obj = self._bus.get_proxy_object(BLUEZ, "/", intro)
        mgr = root_obj.get_interface(OBJMGR_IFACE)

        managed = await mgr.call_get_managed_objects()

        self._player_path = None
        for path, ifaces in managed.items():
            if MP_IFACE in ifaces:
                self._player_path = path
                break

        if self._player_path is None:
            self.connected = False
            return self

        p_intro = await self._bus.introspect(BLUEZ, self._player_path)
        p_obj = self._bus.get_proxy_object(BLUEZ, self._player_path, p_intro)
        self._props = p_obj.get_interface(PROP_IFACE)

        # init
        try:
            tr = await self._props.call_get(MP_IFACE, "Track")
            self._apply_track(tr.value)
            self.connected = True
        except Exception:
            self.connected = False

        self._props.on_properties_changed(self._on_props_changed)
        return self

    def _apply_track(self, d):
        if isinstance(d, dict):
            for k in ["Title", "Artist", "Album", "Duration"]:
                if k in d:
                    v = d[k]
                    self.track[k] = v.value if hasattr(v, "value") else v

    def _on_props_changed(self, iface_name, changed, invalidated):
        if iface_name != MP_IFACE:
            return
        if "Track" in changed:
            self._apply_track(changed["Track"].value)

    def snapshot(self):
        return {
            "connected": bool(self.connected),
            "title": self.track.get("Title", "") or "",
            "artist": self.track.get("Artist", "") or "",
            "album": self.track.get("Album", "") or "",
            "duration_ms": int(self.track.get("Duration", 0) or 0),
        }

async def bt_metadata_loop(meta: BtMetadata):
    # utrzymuj “connected” nawet jak BT się pojawia później
    while True:
        try:
            await meta.start()
        except Exception:
            meta.connected = False
        await asyncio.sleep(2.0)
