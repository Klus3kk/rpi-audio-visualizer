import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import sounddevice as sd
from firmware.player.mpv_player import MpvPlayer
player = MpvPlayer()
player.start()

def make_api(state, audio_engine):
    app = FastAPI(title="Sound Visualizer Control API")

    class PatchState(BaseModel):
        mode: str | None = None          # "analog" | "player"
        effect: str | None = None        # "bars" | "wave"
        brightness: float | None = None  # 0..1
        samplerate: int | None = None
        blocksize: int | None = None
        audio_device: int | None = None  # index z listy ALSA/sounddevice

    def snapshot():
        s = state.get()
        feats = audio_engine.get_features()
        return {
            "mode": s.mode,
            "effect": s.effect,
            "brightness": s.brightness,
            "samplerate": s.samplerate,
            "blocksize": s.blocksize,
            "audio_device": s.audio_device,
            "features": {
                "rms": feats["rms"],
                "bass": feats["bass"],
                "mid": feats["mid"],
                "treble": feats["treble"],
                "bands": feats["bands"].tolist(),
            },
        }

    @app.get("/state")
    def get_state():
        return snapshot()

    @app.patch("/state")
    def patch_state(p: PatchState):
        upd = {}
        if p.mode is not None:
            upd["mode"] = p.mode
        if p.effect is not None:
            upd["effect"] = p.effect
        if p.brightness is not None:
            upd["brightness"] = max(0.0, min(1.0, float(p.brightness)))
        if p.samplerate is not None:
            upd["samplerate"] = int(p.samplerate)
        if p.blocksize is not None:
            upd["blocksize"] = int(p.blocksize)
        if p.audio_device is not None:
            upd["audio_device"] = int(p.audio_device)

        if upd:
            state.update(**upd)

        return snapshot()

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

    @app.post("/shutdown")
    def shutdown():
        state.update(running=False)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(ws: WebSocket):
        await ws.accept()
        try:
            # push state 10x/sek + odbieranie patchy (opcjonalnie)
            while state.get().running:
                await ws.send_json(snapshot())
                try:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=0.0)
                    # jeśli klient wyśle patch, obsłuż
                    if isinstance(msg, dict):
                        # minimalnie: effect/mode/brightness
                        upd = {}
                        if "mode" in msg: upd["mode"] = msg["mode"]
                        if "effect" in msg: upd["effect"] = msg["effect"]
                        if "brightness" in msg:
                            b = float(msg["brightness"])
                            upd["brightness"] = max(0.0, min(1.0, b))
                        if "audio_device" in msg: upd["audio_device"] = int(msg["audio_device"])
                        if "samplerate" in msg: upd["samplerate"] = int(msg["samplerate"])
                        if "blocksize" in msg: upd["blocksize"] = int(msg["blocksize"])
                        if upd:
                            state.update(**upd)
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            return

    return app

class PlayReq(BaseModel):
    path: str

@app.post("/player/play")
def player_play(p: PlayReq):
    state.update(mode="player")
    return {"ok": True, "resp": player.load(p.path)}

@app.post("/player/pause")
def player_pause():
    return {"ok": True, "resp": player.toggle_pause()}

@app.post("/player/next")
def player_next():
    return {"ok": True, "resp": player.next()}

@app.post("/player/prev")
def player_prev():
    return {"ok": True, "resp": player.prev()}
