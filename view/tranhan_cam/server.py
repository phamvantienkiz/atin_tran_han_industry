"""Lightweight FastAPI proxy & static server for ATIN Tran Han Live View."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "cameras.json"

load_dotenv(BASE_DIR / ".env")

NVR_HOST = os.getenv("NVR_HOST", "").strip()
NVR_PORT = int(os.getenv("NVR_PORT", "80"))
NVR_USER = os.getenv("NVR_USER", "").strip()
NVR_PASS = os.getenv("NVR_PASS", "").strip()
if not (NVR_HOST and NVR_USER and NVR_PASS):
    raise RuntimeError(
        "Thiếu cấu hình NVR_HOST, NVR_USER hoặc NVR_PASS trong file .env "
        "(copy từ .env.example để cấu hình)."
    )
NVR_BASE_URL = f"http://{NVR_HOST}:{NVR_PORT}"

DEFAULT_CAMERAS: list[dict[str, Any]] = [
    {
        "id": "ch16",
        "channel": 16,
        "name": "Tăng trọng 1",
        "note": "Khu vực máy tăng trọng 1",
        "subtype": 1,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
    {
        "id": "ch17",
        "channel": 17,
        "name": "Tăng trọng 2",
        "note": "Khu vực máy tăng trọng 2",
        "subtype": 1,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
    {
        "id": "ch18",
        "channel": 18,
        "name": "Tăng trọng 3",
        "note": "Khu vực máy tăng trọng 3",
        "subtype": 1,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
    {
        "id": "ch21",
        "channel": 21,
        "name": "Định hình 2",
        "note": "Khu vực định hình 2",
        "subtype": 1,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
]


def load_cameras() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        save_cameras(DEFAULT_CAMERAS)
        return [dict(c) for c in DEFAULT_CAMERAS]
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return [dict(c) for c in DEFAULT_CAMERAS]


def save_cameras(cameras: list[dict[str, Any]]) -> None:
    DATA_FILE.write_text(
        json.dumps(cameras, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_camera(cam_id: str) -> dict[str, Any]:
    for cam in load_cameras():
        if cam["id"] == cam_id:
            return cam
    raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")


def make_auth() -> httpx.DigestAuth:
    return httpx.DigestAuth(NVR_USER, NVR_PASS)


class CameraCreate(BaseModel):
    channel: int = Field(ge=1, le=128)
    name: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=240)
    subtype: int = Field(default=1, ge=0, le=2)
    mode: str = Field(default="mjpeg", pattern="^(mjpeg|snapshot)$")
    enabled: bool = True


class CameraUpdate(BaseModel):
    channel: int | None = Field(default=None, ge=1, le=128)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=240)
    subtype: int | None = Field(default=None, ge=0, le=2)
    mode: str | None = Field(default=None, pattern="^(mjpeg|snapshot)$")
    enabled: bool | None = None


class ZonePoint(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ZonePayload(BaseModel):
    points: list[ZonePoint]


app = FastAPI(title="ATIN Tran Han Live View", version="0.1.0")


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    return {
        "nvr_host": NVR_HOST,
        "nvr_port": NVR_PORT,
        "project": "Nhà máy Thủy sản Trần Hân",
    }


@app.get("/api/cameras")
async def list_cameras() -> list[dict[str, Any]]:
    return load_cameras()


@app.post("/api/cameras", status_code=201)
async def create_camera(payload: CameraCreate) -> dict[str, Any]:
    cameras = load_cameras()
    cam_id = f"ch{payload.channel}"
    if any(c["id"] == cam_id for c in cameras):
        cam_id = f"ch{payload.channel}_{int(time.time()) % 10000}"
    cam = {
        "id": cam_id,
        "channel": payload.channel,
        "name": payload.name.strip(),
        "note": payload.note.strip(),
        "subtype": payload.subtype,
        "mode": payload.mode,
        "enabled": payload.enabled,
        "zone": [],
    }
    cameras.append(cam)
    save_cameras(cameras)
    return cam


@app.put("/api/cameras/{cam_id}")
async def update_camera(cam_id: str, payload: CameraUpdate) -> dict[str, Any]:
    cameras = load_cameras()
    for cam in cameras:
        if cam["id"] == cam_id:
            updates = payload.model_dump(exclude_none=True)
            if "name" in updates:
                updates["name"] = updates["name"].strip()
            if "note" in updates:
                updates["note"] = updates["note"].strip()
            cam.update(updates)
            save_cameras(cameras)
            return cam
    raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")


@app.delete("/api/cameras/{cam_id}")
async def delete_camera(cam_id: str) -> dict[str, str]:
    cameras = load_cameras()
    filtered = [c for c in cameras if c["id"] != cam_id]
    if len(filtered) == len(cameras):
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")
    save_cameras(filtered)
    return {"status": "deleted", "id": cam_id}


@app.put("/api/cameras/{cam_id}/zone")
async def save_zone(cam_id: str, payload: ZonePayload) -> dict[str, Any]:
    cameras = load_cameras()
    for cam in cameras:
        if cam["id"] == cam_id:
            cam["zone"] = [p.model_dump() for p in payload.points]
            save_cameras(cameras)
            return cam
    raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")


@app.get("/api/cameras/{cam_id}/snapshot.jpg")
async def get_snapshot(cam_id: str) -> Response:
    cam = find_camera(cam_id)
    url = f"{NVR_BASE_URL}/cgi-bin/snapshot.cgi?channel={cam['channel']}"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(auth=make_auth(), timeout=8.0) as client:
            resp = await client.get(url)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối NVR: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Không lấy được ảnh snapshot")

    latency_ms = round((time.perf_counter() - t0) * 1000)
    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "image/jpeg"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Latency-Ms": str(latency_ms),
        },
    )


@app.get("/api/cameras/{cam_id}/probe")
async def probe_camera(cam_id: str) -> dict[str, Any]:
    cam = find_camera(cam_id)
    url = f"{NVR_BASE_URL}/cgi-bin/snapshot.cgi?channel={cam['channel']}"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(auth=make_auth(), timeout=6.0) as client:
            resp = await client.get(url)
        latency_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "id": cam_id,
            "online": resp.status_code == 200,
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "bytes": len(resp.content),
        }
    except httpx.RequestError as exc:
        return {
            "id": cam_id,
            "online": False,
            "error": str(exc),
            "latency_ms": None,
        }


@app.get("/api/cameras/{cam_id}/mjpeg")
async def stream_mjpeg(
    cam_id: str,
    subtype: int | None = Query(default=None, ge=0, le=2),
) -> StreamingResponse:
    cam = find_camera(cam_id)
    stream_sub = cam.get("subtype", 1) if subtype is None else subtype
    url = f"{NVR_BASE_URL}/cgi-bin/mjpg/video.cgi?channel={cam['channel']}&subtype={stream_sub}"

    client = httpx.AsyncClient(auth=make_auth(), timeout=httpx.Timeout(10.0, read=30.0))
    req = client.build_request("GET", url)
    try:
        upstream = await client.send(req, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Lỗi luồng MJPEG: {exc}") from exc

    if upstream.status_code != 200:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=upstream.status_code, detail="NVR từ chối luồng MJPEG")

    content_type = upstream.headers.get(
        "content-type",
        "multipart/x-mixed-replace; boundary=myboundary",
    )

    async def body_iterator():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=8192):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body_iterator(),
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


app.mount("/js", StaticFiles(directory=BASE_DIR / "js"), name="js")


@app.get("/styles.css")
async def styles() -> FileResponse:
    return FileResponse(BASE_DIR / "styles.css")
