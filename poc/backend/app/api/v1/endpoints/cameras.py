import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse

from app.ai.display_pipeline import DisplayAndSyncPipeline
from app.ai.nvr_stream import NvrStreamManager
from app.api.deps import (
    get_camera_service,
    get_display_pipeline,
    get_media_service,
    get_nvr_stream_manager,
)
from app.core.config import settings
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
    display_pipeline: Annotated[DisplayAndSyncPipeline, Depends(get_display_pipeline)],
    subtype: int | None = Query(default=None, ge=0, le=2),
    view: str = Query(default="grid", pattern="^(grid|focus)$"),
) -> StreamingResponse:
    cam = service.get_camera(cam_id)
    requested_sub = int(cam.get("subtype", 0)) if subtype is None else subtype

    # Fast path: serve event-driven synced/encoded JPEG from DisplayAndSyncPipeline (or raw RAM packet)
    cached_pkt = stream_manager.latest(cam_id)
    if cached_pkt is not None and cached_pkt.subtype == requested_sub:
        valve_sec = max(0.05, settings.STREAM_VALVE_MS / 1000.0)

        async def ram_iterator() -> AsyncIterator[bytes]:
            ev = display_pipeline.register_mjpeg_waiter(cam_id)
            last_frame_id = -1
            try:
                while not await request.is_disconnected():
                    df = display_pipeline.latest_released(cam_id)
                    if df is not None and df.frame_id != last_frame_id:
                        last_frame_id = df.frame_id
                        jpg = display_pipeline.encode_for_viewer(df, view)
                        if jpg:
                            yield _format_mjpeg_part(jpg)
                    else:
                        pkt = stream_manager.latest(cam_id)
                        if pkt is None or pkt.subtype != requested_sub:
                            break
                        if df is None and pkt.seq != last_frame_id:
                            last_frame_id = pkt.seq
                            yield _format_mjpeg_part(pkt.jpeg_bytes)

                    ev.clear()
                    try:
                        await asyncio.wait_for(ev.wait(), timeout=valve_sec)
                    except asyncio.TimeoutError:
                        # Release valve: flush latest frame so video never stalls if AI slows down
                        latest_df = display_pipeline.latest_decoded(cam_id)
                        if latest_df is not None and latest_df.frame_id != last_frame_id:
                            display_pipeline.record_valve_timeout(cam_id)
                            last_frame_id = latest_df.frame_id
                            jpg = display_pipeline.encode_for_viewer(latest_df, view)
                            if jpg:
                                yield _format_mjpeg_part(jpg)
            finally:
                display_pipeline.unregister_mjpeg_waiter(cam_id, ev)

        return StreamingResponse(
            ram_iterator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "X-Stream-Source": f"ram-synced-{view}",
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
            "Cache-Control": "no-store",
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
