from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse

from app.api.deps import get_camera_service, get_media_service
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
) -> Response:
    content, media_type, latency_ms = await service.fetch_snapshot(cam_id)
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


@router.get("/{cam_id}/mjpeg")
async def stream_mjpeg(
    cam_id: str,
    service: Annotated[CameraService, Depends(get_camera_service)],
    subtype: int | None = Query(default=None, ge=0, le=2),
) -> StreamingResponse:
    url, auth = service.build_mjpeg_request(cam_id, subtype)
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
