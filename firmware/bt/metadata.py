import asyncio
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

BLUEZ = "org.bluez"
MP_IFACE = "org.bluez.MediaPlayer1"
PROP_IFACE = "org.freedesktop.DBus.Properties"
OBJMGR_IFACE = "org.freedesktop.DBus.ObjectManager"

class BtMetadata:
    def __init__(self):
        self.track = {"Title": "", "Artist": "", "Album": "", "Duration": 0, "AlbumArtURL": ""}
        self.connected = False
        self._bus = None
        self._props = None
        self._player_path = None

    async def start(self):
        self.connected = False
        self._props = None
        self._player_path = None

        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        intro = await self._bus.introspect(BLUEZ, "/")
        root_obj = self._bus.get_proxy_object(BLUEZ, "/", intro)
        mgr = root_obj.get_interface(OBJMGR_IFACE)

        managed = await mgr.call_get_managed_objects()

        for path, ifaces in managed.items():
            if MP_IFACE in ifaces:
                self._player_path = path
                break

        if self._player_path is None:
            return self

        p_intro = await self._bus.introspect(BLUEZ, self._player_path)
        p_obj = self._bus.get_proxy_object(BLUEZ, self._player_path, p_intro)
        self._props = p_obj.get_interface(PROP_IFACE)

        try:
            # GetAll jest stabilniejsze niż Get("Track") na niektórych telefonach
            allp = await self._props.call_get_all(MP_IFACE)
            if "Track" in allp:
                self._apply_track(allp["Track"].value)
            self.connected = True
        except Exception:
            self.connected = False

        self._props.on_properties_changed(self._on_props_changed)
        return self

    def _norm_artist(self, a):
        if a is None:
            return ""
        if isinstance(a, (list, tuple)):
            return ", ".join([str(x) for x in a if x])
        return str(a)

    def _apply_track(self, d):
        if not isinstance(d, dict):
            return
        def val(x):
            return x.value if hasattr(x, "value") else x

        if "Title" in d:
            self.track["Title"] = str(val(d["Title"]) or "")
        if "Artist" in d:
            self.track["Artist"] = self._norm_artist(val(d["Artist"]))
        if "Album" in d:
            self.track["Album"] = str(val(d["Album"]) or "")
        if "Duration" in d:
            try:
                self.track["Duration"] = int(val(d["Duration"]) or 0)
            except Exception:
                self.track["Duration"] = 0
        if "AlbumArtURL" in d:
            self.track["AlbumArtURL"] = str(val(d["AlbumArtURL"]) or "")

    def _on_props_changed(self, iface_name, changed, invalidated):
        if iface_name != MP_IFACE:
            return
        if "Track" in changed:
            try:
                self._apply_track(changed["Track"].value)
                self.connected = True
            except Exception:
                pass

    def snapshot(self):
        return {
            "connected": bool(self.connected),
            "title": self.track.get("Title", "") or "",
            "artist": self.track.get("Artist", "") or "",
            "album": self.track.get("Album", "") or "",
            "duration_ms": int(self.track.get("Duration", 0) or 0),
            "cover_url": self.track.get("AlbumArtURL", "") or "",
        }

async def bt_metadata_loop(meta: BtMetadata):
    while True:
        try:
            await meta.start()
        except Exception:
            meta.connected = False
        await asyncio.sleep(2.0)
