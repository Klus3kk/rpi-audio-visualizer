import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import sounddevice as sd
from firmware.player.mpv_player import MpvPlayer
from firmware.audio.routing import input_for_mode
from firmware.bt.metadata import BtMetadata, bt_metadata_loop
import os
from pathlib import Path

def make_api(state, audio_engine):
    app = FastAPI(title="Sound Visualizer Control API")

    bt_meta = BtMetadata()

    mpv = MpvPlayer()
    
    MUSIC_ROOT = Path(os.environ.get("MUSIC_ROOT", "/home/pi/Music")).resolve()
    ALLOWED_EXT = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac"}

    try:
        mpv.start()
    except Exception:
        # jeśli mpv nie zainstalowane lub IPC fail, API i tak ma działać
        mpv = None

    class PatchState(BaseModel):
        mode: str | None = None              # "mic" | "bluetooth" | "local"
        effect: str | None = None            # "bars" | "wave" | "vu" | "scope" | "radial" | "fire"
        brightness: float | None = None      # 0..1
        intensity: float | None = None       # 0..1
        gain: float | None = None            # 0.1..8
        smoothing: float | None = None       # 0..0.95
        color_mode: str | None = None        # auto/mono/rainbow

        passthrough: bool | None = None      # mic passthrough
        input_device: int | None = None      # sounddevice input index
        output_device: int | None = None     # sounddevice output index

        samplerate: int | None = None
        blocksize: int | None = None

    def snapshot():
        s = state.get()
        feats = audio_engine.get_features()
        return {
            "mode": s.mode,
            "effect": s.effect,
            "brightness": s.brightness,
            "intensity": s.intensity,
            "gain": s.gain,
            "smoothing": s.smoothing,
            "color_mode": s.color_mode,
            "passthrough": s.passthrough,
            "input_device": s.input_device,
            "output_device": s.output_device,
            "samplerate": s.samplerate,
            "blocksize": s.blocksize,
            "features": {
                "rms": feats["rms"],
                "bass": feats["bass"],
                "mid": feats["mid"],
                "treble": feats["treble"],
                "bands": feats["bands"].tolist(),
            },
        }

    @app.on_event("startup")
    async def _startup():
        # background task: BT metadata polling/reconnect
        asyncio.create_task(bt_metadata_loop(bt_meta))

    @app.get("/state")
    def get_state():
        return snapshot()

    @app.patch("/state")
    def patch_state(p: PatchState):
        upd = {}

        if p.mode is not None:
            upd["mode"] = p.mode
            # auto-select input device dla trybu
            auto_in = input_for_mode(p.mode)
            if auto_in is not None:
                upd["input_device"] = auto_in


        if p.effect is not None:
            upd["effect"] = p.effect

        if p.brightness is not None:
            upd["brightness"] = max(0.0, min(1.0, float(p.brightness)))

        if p.intensity is not None:
            upd["intensity"] = max(0.0, min(1.0, float(p.intensity)))

        if p.gain is not None:
            upd["gain"] = max(0.1, min(8.0, float(p.gain)))

        if p.smoothing is not None:
            upd["smoothing"] = max(0.0, min(0.95, float(p.smoothing)))

        if p.color_mode is not None:
            upd["color_mode"] = p.color_mode

        if p.passthrough is not None:
            upd["passthrough"] = bool(p.passthrough)

        if p.input_device is not None:
            upd["input_device"] = int(p.input_device)

        if p.output_device is not None:
            upd["output_device"] = int(p.output_device)

        if p.samplerate is not None:
            upd["samplerate"] = int(p.samplerate)

        if p.blocksize is not None:
            upd["blocksize"] = int(p.blocksize)

        if upd:
            state.update(**upd)

        return snapshot()

    @app.get("/effects")
    def effects():
        return {"effects": ["bars", "wave", "vu", "scope", "radial", "fire"]}

    @app.get("/devices/audio")
    def list_audio_devices():
        devs = sd.query_devices()
        out = []
        for i, d in enumerate(devs):
            out.append({
                "index": i,
                "name": d.get("name"),
                "max_input_channels": d.get("max_input_channels"),
                "max_output_channels": d.get("max_output_channels"),
                "default_samplerate": d.get("default_samplerate"),
                "hostapi": d.get("hostapi"),
            })
        return {"devices": out}

    @app.get("/nowplaying")
    def nowplaying():
        s = state.get()
        if s.mode == "bluetooth":
            return {"source": "bluetooth", **bt_meta.snapshot()}
        if s.mode == "local":
            if mpv is None:
                return {"source": "local", "connected": False, "title": "", "artist": "", "album": "", "duration_ms": 0}
            npv = mpv.nowplaying()
            return {"source": "local", "connected": npv["connected"], "title": npv["title"], "artist": npv["artist"], "album": npv["album"], "duration_ms": 0, "paused": npv["paused"]}
        return {"source": s.mode, "connected": False, "title": "", "artist": "", "album": "", "duration_ms": 0}

    @app.post("/shutdown")
    def shutdown():
        state.update(running=False)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(ws: WebSocket):
        await ws.accept()
        try:
            while state.get().running:
                # state + nowplaying w jednym pushu
                payload = snapshot()
                payload["nowplaying"] = await asyncio.to_thread(lambda: nowplaying())
                await ws.send_json(payload)

                try:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=0.0)
                    if isinstance(msg, dict):
                        # szybki patch przez WS
                        patch = {}
                        for k in ["mode","effect","brightness","intensity","gain","smoothing","color_mode","passthrough","input_device","output_device","samplerate","blocksize"]:
                            if k in msg:
                                patch[k] = msg[k]
                        if patch:
                            # reuse patch logic: call state.update with clamps minimalnie
                            # (tu prosto; pełne clampy masz w PATCH /state)
                            state.update(**patch)
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            return

    class PlayReq(BaseModel):
        path: str

    @app.post("/player/play")
    def player_play(p: PlayReq):
        state.update(mode="local")  # przełącz tryb na local
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}
        return {"ok": True, "resp": mpv.load(p.path)}

    @app.post("/player/add")
    def player_add(p: PlayReq):
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}
        return {"ok": True, "resp": mpv.add(p.path)}

    @app.post("/player/pause")
    def player_pause():
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}
        return {"ok": True, "resp": mpv.toggle_pause()}

    @app.post("/player/next")
    def player_next():
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}
        return {"ok": True, "resp": mpv.next()}

    @app.post("/player/prev")
    def player_prev():
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}
        return {"ok": True, "resp": mpv.prev()}

    @app.post("/player/stop")
    def player_stop():
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}
        return {"ok": True, "resp": mpv.stop_playback()}
    
    
    @app.get("/library")
    def library(path: str = ""):
        base = MUSIC_ROOT
        p = (base / path).resolve()

        # bezpieczeństwo: nie wychodź poza root
        if not str(p).startswith(str(base)):
            return {"ok": False, "error": "invalid path"}

        if not p.exists():
            return {"ok": False, "error": "not found"}

        if p.is_file():
            return {"ok": True, "type": "file", "path": str(p), "name": p.name}

        dirs = []
        files = []
        for entry in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry.relative_to(base))})
            else:
                if entry.suffix.lower() in ALLOWED_EXT:
                    files.append({"name": entry.name, "path": str(entry.relative_to(base)), "ext": entry.suffix.lower()})

        return {"ok": True, "type": "dir", "root": str(base), "path": str(p.relative_to(base)) if p != base else "", "dirs": dirs, "files": files}

    @app.post("/player/clear")
    def player_clear():
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}
        # mpv: clear playlist poprzez komendę playlist-clear
        return {"ok": True, "resp": mpv._send({"command": ["playlist-clear"]})}

    @app.post("/player/enqueue_folder")
    def player_enqueue_folder(path: str = ""):
        if mpv is None:
            return {"ok": False, "error": "mpv not available"}

        base = MUSIC_ROOT
        folder = (base / path).resolve()
        if not str(folder).startswith(str(base)) or not folder.exists() or not folder.is_dir():
            return {"ok": False, "error": "invalid folder"}

        # dodaj wszystkie pliki audio z folderu (bez rekursji)
        added = 0
        for entry in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
            if entry.is_file() and entry.suffix.lower() in ALLOWED_EXT:
                mpv.add(str(entry))
                added += 1

        state.update(mode="local")
        auto_in = input_for_mode("local")
        if auto_in is not None:
            state.update(input_device=auto_in)

        return {"ok": True, "added": added}

    
    return app
