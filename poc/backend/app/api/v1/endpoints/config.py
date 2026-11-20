from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_detection_service
from app.core.config import settings
from app.services.detection_service import DetectionService

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config(
    detection_service: Annotated[DetectionService, Depends(get_detection_service)],
) -> dict[str, Any]:
    return {
        "nvr_host": settings.NVR_HOST,
        "nvr_port": settings.NVR_PORT,
        "project": settings.PROJECT_DISPLAY_NAME,
        "environment": settings.ENVIRONMENT,
        "atin_vms_enabled": settings.ATIN_VMS_ENABLED,
        "timeline_window_sec": settings.AI_TIMELINE_WINDOW_SECONDS,
        "ws_path": f"{settings.API_V1_PREFIX}/ws/detections",
        "ai_runtime": settings.AI_RUNTIME,
        "active_provider": detection_service.active_provider,
        "grace_seconds": settings.AI_PRESENCE_GRACE_SECONDS,
        "warning_seconds": settings.AI_PRESENCE_WARNING_SECONDS,
    }
