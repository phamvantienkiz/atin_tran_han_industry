"""Application service container (decouples lifecycle from FastAPI routes)."""

from __future__ import annotations

from functools import lru_cache

from app.ai.worker import PersonZoneDetector
from app.core.config import settings
from app.repositories.camera_repository import JsonCameraRepository
from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService
from app.services.media_service import MediaService


class ServiceContainer:
    """Holds application-scoped repositories, workers, and services."""

    def __init__(self) -> None:
        self.camera_repo = JsonCameraRepository(settings.cameras_file_path)
        self.camera_service = CameraService(
            repo=self.camera_repo,
            nvr_base_url=settings.nvr_base_url,
            nvr_user=settings.NVR_USER,
            nvr_pass=settings.NVR_PASS,
            nvr_configured=settings.nvr_configured,
        )
        self.detector = PersonZoneDetector(
            model_path=settings.model_file_path,
            nvr_base_url=settings.nvr_base_url,
            nvr_user=settings.NVR_USER,
            nvr_pass=settings.NVR_PASS,
            load_cameras_fn=self.camera_repo.list_all,
            conf=settings.AI_CONF_THRESHOLD,
            imgsz=settings.AI_IMGSZ,
            interval_sec=settings.AI_INTERVAL_SEC,
            focus_interval_sec=settings.AI_FOCUS_INTERVAL_SEC,
            focus_ttl_sec=settings.AI_FOCUS_TTL_SEC,
            confirm_seconds=settings.AI_CONFIRM_SECONDS,
            cooldown_seconds=settings.AI_EVENT_COOLDOWN_SECONDS,
        )
        self.detection_service = DetectionService(
            detector=self.detector,
            camera_service=self.camera_service,
        )
        self.media_service = MediaService(
            storages_dir=settings.storages_path,
            nvr_base_url=settings.nvr_base_url,
            nvr_user=settings.NVR_USER,
            nvr_pass=settings.NVR_PASS,
        )


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return ServiceContainer()
