from typing import Any

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config() -> dict[str, Any]:
    return {
        "nvr_host": settings.NVR_HOST,
        "nvr_port": settings.NVR_PORT,
        "project": settings.PROJECT_DISPLAY_NAME,
        "environment": settings.ENVIRONMENT,
        "atin_vms_enabled": settings.ATIN_VMS_ENABLED,
    }
