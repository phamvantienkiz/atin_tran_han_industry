from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_detection_service
from app.schemas.detection import FocusDetectionPayload
from app.services.detection_service import DetectionService

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("")
def get_detections(
    service: Annotated[DetectionService, Depends(get_detection_service)],
    focus_cam_id: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    return service.get_detections(focus_cam_id=focus_cam_id)


@router.post("/focus")
def set_detection_focus(
    payload: FocusDetectionPayload,
    service: Annotated[DetectionService, Depends(get_detection_service)],
) -> dict[str, Any]:
    return service.set_focus(payload.cam_id)
