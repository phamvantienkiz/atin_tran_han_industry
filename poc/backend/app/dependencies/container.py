"""Application service container (decouples lifecycle from FastAPI routes)."""

from __future__ import annotations

from functools import lru_cache

from app.ai.nvr_stream import NvrStreamManager
from app.ai.worker import PersonZoneDetector
from app.core.config import settings
from app.repositories.camera_repository import JsonCameraRepository
from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService
from app.services.media_service import MediaService
from app.services.ws_hub import DetectionWsHub


class ServiceContainer:
    """Holds application-scoped repositories, stream managers, workers, and services."""

    def __init__(self) -> None:
        self.camera_repo = JsonCameraRepository(settings.cameras_file_path)
        self.ws_hub = DetectionWsHub(max_hz=settings.WS_PUSH_MAX_HZ)
        self.nvr_stream_manager = NvrStreamManager(
            nvr_base_url=settings.nvr_base_url,
            nvr_user=settings.NVR_USER,
            nvr_pass=settings.NVR_PASS,
            nvr_configured=settings.nvr_configured,
            fps_limit=settings.NVR_STREAM_FPS_LIMIT,
        )
        self.camera_service = CameraService(
            repo=self.camera_repo,
            nvr_base_url=settings.nvr_base_url,
            nvr_user=settings.NVR_USER,
            nvr_pass=settings.NVR_PASS,
            nvr_configured=settings.nvr_configured,
            nvr_stream_manager=self.nvr_stream_manager,
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
            runtime=settings.AI_RUNTIME,
            vram_limit_mb=settings.AI_VRAM_LIMIT_MB,
            target_fps=settings.AI_TARGET_FPS,
            anchor_mode=settings.AI_ANCHOR_MODE,
            grace_seconds=settings.AI_PRESENCE_GRACE_SECONDS,
            warning_seconds=settings.AI_PRESENCE_WARNING_SECONDS,
            timeline_window_seconds=settings.AI_TIMELINE_WINDOW_SECONDS,
            drum_stop_alert_seconds=settings.AI_DRUM_STOP_ALERT_SECONDS,
            nvr_stream_manager=self.nvr_stream_manager,
            on_update=self.ws_hub.publish_from_thread,
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
