import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response

from app.api.deps import get_media_service
from app.schemas.media import ExtractFramesPayload
from app.services.media_service import MediaService

router = APIRouter(tags=["storages"])


@router.get("/records/active")
def list_active_records(
    service: Annotated[MediaService, Depends(get_media_service)],
) -> list[dict[str, Any]]:
    return service.active_jobs()


@router.get("/records/{job_id}")
def get_record_job(
    job_id: str,
    service: Annotated[MediaService, Depends(get_media_service)],
) -> dict[str, Any]:
    return service.get_job(job_id)


@router.get("/storages/videos")
def list_videos(
    service: Annotated[MediaService, Depends(get_media_service)],
) -> list[dict[str, Any]]:
    return service.list_videos()


@router.get("/storages/videos/{filename}/download")
def download_video(
    filename: str,
    service: Annotated[MediaService, Depends(get_media_service)],
) -> FileResponse:
    target = service.get_video_path(filename)
    return FileResponse(target, media_type="video/mp4", filename=target.name)


@router.delete("/storages/videos/{filename}")
def delete_video(
    filename: str,
    service: Annotated[MediaService, Depends(get_media_service)],
) -> dict[str, str]:
    service.delete_video(filename)
    return {"status": "deleted", "filename": filename}


@router.post("/storages/videos/{filename}/extract")
async def extract_frames(
    filename: str,
    payload: ExtractFramesPayload,
    service: Annotated[MediaService, Depends(get_media_service)],
) -> dict[str, Any]:
    return await asyncio.to_thread(service.extract_frames, filename, payload.skip_frames)


@router.get("/storages/frames")
def list_frame_sets(
    service: Annotated[MediaService, Depends(get_media_service)],
) -> list[dict[str, Any]]:
    return service.list_frame_sets()


@router.get("/storages/frames/{folder}/preview/{image_name}")
def preview_frame(
    folder: str,
    image_name: str,
    service: Annotated[MediaService, Depends(get_media_service)],
) -> FileResponse:
    target = service.get_frame_preview_path(folder, image_name)
    return FileResponse(target, media_type="image/jpeg")


@router.get("/storages/frames/{folder}/download.zip")
async def download_frames_zip(
    folder: str,
    service: Annotated[MediaService, Depends(get_media_service)],
) -> Response:
    safe_folder, data = await asyncio.to_thread(service.build_frames_zip_bytes, folder)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_folder}.zip"'},
    )


@router.delete("/storages/frames/{folder}")
def delete_frame_set(
    folder: str,
    service: Annotated[MediaService, Depends(get_media_service)],
) -> dict[str, str]:
    service.delete_frame_set(folder)
    return {"status": "deleted", "folder": folder}
