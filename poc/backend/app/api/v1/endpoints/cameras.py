import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse

from app.ai.grid_cache import GridFrameCache
from app.ai.nvr_stream import NvrStreamManager
from app.api.deps import (
    get_camera_service,
    get_grid_cache,
    get_media_service,
    get_nvr_stream_manager,
)
from app.schemas.camera import CameraCreate, CameraUpdate, ZonePayload
from app.schemas.media import RecordStartPayload
from app.services.camera_service import CameraService
from app.services.media_service import MediaService

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("")
def list_cameras(
    service: Annotated[CameraService, Depends(get_camera_service)],
    enabled: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
) -> list[dict[str, Any]]:
    return service.list_cameras(enabled=enabled, search=search)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_camera(
    payload: CameraCreate,
    service: Annotated[CameraService, Depends(get_camera_service)],
) -> dict[str, Any]:
    return service.create_camera(payload)


@router.put("/{cam_id}")
def update_camera(
    cam_id: str,
    payload: CameraUpdate,
    service: Annotated[CameraService, Depends(get_camera_service)],
) -> dict[str, Any]:
    return service.update_camera(cam_id, payload)


@router.delete("/{cam_id}")
def delete_camera(
    cam_id: str,
    service: Annotated[CameraService, Depends(get_camera_service)],
) -> dict[str, str]:
    return service.delete_camera(cam_id)


@router.put("/{cam_id}/zone")
def save_zone(
    cam_id: str,
    payload: ZonePayload,
    service: Annotated[CameraService, Depends(get_camera_service)],
) -> dict[str, Any]:
    return service.save_zone(cam_id, payload.points)


@router.get("/{cam_id}/snapshot.jpg")
async def get_snapshot(
    cam_id: str,
    service: Annotated[CameraService, Depends(get_camera_service)],
    direct: bool = Query(default=False),
) -> Response:
    content, media_type, latency_ms = await service.fetch_snapshot(cam_id, direct=direct)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Latency-Ms": str(latency_ms),
        },
    )


@router.get("/{cam_id}/probe")
async def probe_camera(
    cam_id: str,
    service: Annotated[CameraService, Depends(get_camera_service)],
) -> dict[str, Any]:
    return await service.probe_camera(cam_id)


def _format_mjpeg_part(jpeg_bytes: bytes) -> bytes:
    header = (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n"
        b"Content-Length: " + str(len(jpeg_bytes)).encode("ascii") + b"\r\n\r\n"
    )
    return header + jpeg_bytes + b"\r\n"


@router.get("/{cam_id}/mjpeg")
async def stream_mjpeg(
    cam_id: str,
    request: Request,
    service: Annotated[CameraService, Depends(get_camera_service)],
    stream_manager: Annotated[NvrStreamManager, Depends(get_nvr_stream_manager)],
    grid_cache: Annotated[GridFrameCache, Depends(get_grid_cache)],
    subtype: int | None = Query(default=None, ge=0, le=2),
    view: str = Query(default="grid", pattern="^(grid|focus)$"),
) -> StreamingResponse:
    cam = service.get_camera(cam_id)
    requested_sub = int(cam.get("subtype", 0)) if subtype is None else subtype
    stream_headers_base = {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Accel-Buffering": "no",
    }

    cached_pkt = stream_manager.latest(cam_id)
    if cached_pkt is not None and cached_pkt.subtype == requested_sub:
        # Grid View on main stream (1080p): serve shared Latest-Frame resized JPEG (off asyncio loop)
        if view == "grid" and requested_sub == 0:

            async def grid_iterator() -> AsyncIterator[bytes]:
                ev = grid_cache.register_grid_waiter(cam_id, initial_pkt=cached_pkt)
                last_seq = -1
                try:
                    while not await request.is_disconnected():
                        raw_pkt = stream_manager.latest(cam_id)
                        if raw_pkt is None or raw_pkt.subtype != requested_sub:
                            break
                        gf = grid_cache.latest_grid(cam_id)
                        if gf is not None and gf.subtype == requested_sub and gf.seq != last_seq:
                            last_seq = gf.seq
                            yield _format_mjpeg_part(gf.jpeg_bytes)
                        ev.clear()
                        try:
                            await asyncio.wait_for(ev.wait(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                finally:
                    grid_cache.unregister_grid_waiter(cam_id, ev)

            return StreamingResponse(
                grid_iterator(),
                media_type="multipart/x-mixed-replace; boundary=frame",
                headers={
                    **stream_headers_base,
                    "X-Stream-Source": "ram-grid-cache",
                },
            )

        # Focus View (or already-small sub-stream): direct passthrough of raw NVR JPEG bytes
        async def ram_iterator() -> AsyncIterator[bytes]:
            ev = stream_manager.register_waiter(cam_id)
            grid_cache.register_focus_viewer(cam_id)
            last_seq = -1
            try:
                while not await request.is_disconnected():
                    pkt = stream_manager.latest(cam_id)
                    if pkt is None or pkt.subtype != requested_sub:
                        break
                    if pkt.seq != last_seq:
                        last_seq = pkt.seq
                        yield _format_mjpeg_part(pkt.jpeg_bytes)
                    ev.clear()
                    try:
                        await asyncio.wait_for(ev.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
            finally:
                grid_cache.unregister_focus_viewer(cam_id)
                stream_manager.unregister_waiter(cam_id, ev)

        return StreamingResponse(
            ram_iterator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                **stream_headers_base,
                "X-Stream-Source": "ram-direct",
            },
        )

    # Fallback path: direct proxy to NVR (e.g. cold start or Focus Modal switching subtype)
    url, auth = service.build_mjpeg_request(cam_id, requested_sub)
    client = httpx.AsyncClient(auth=auth, timeout=httpx.Timeout(10.0, read=30.0))
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

    async def body_iterator() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=8192):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body_iterator(),
        media_type=content_type,
        headers={
            **stream_headers_base,
            "X-Stream-Source": "nvr-direct",
        },
    )


@router.post("/{cam_id}/record/start", status_code=status.HTTP_202_ACCEPTED)
def start_record(
    cam_id: str,
    payload: RecordStartPayload,
    camera_service: Annotated[CameraService, Depends(get_camera_service)],
    media_service: Annotated[MediaService, Depends(get_media_service)],
) -> dict[str, Any]:
    cam = camera_service.get_camera(cam_id)
    return media_service.start_record(cam, payload.duration_minutes, payload.subtype)


@router.post("/{cam_id}/record/stop")
def stop_record(
    cam_id: str,
    camera_service: Annotated[CameraService, Depends(get_camera_service)],
    media_service: Annotated[MediaService, Depends(get_media_service)],
) -> dict[str, Any]:
    camera_service.get_camera(cam_id)
    return media_service.stop_record(cam_id)
