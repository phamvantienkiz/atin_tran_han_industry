"""Detection orchestration service."""

from __future__ import annotations

from typing import Any

from app.ai.worker import PersonZoneDetector
from app.services.camera_service import CameraService


class DetectionService:
    """Exposes live AI detections, focus control, and stats reset without HTTP coupling."""

    def __init__(self, detector: PersonZoneDetector, camera_service: CameraService) -> None:
        self._detector = detector
        self._camera_service = camera_service

    @property
    def active_provider(self) -> str:
        return self._detector.active_provider

    def start(self) -> None:
        self._detector.start()

    def stop(self) -> None:
        self._detector.stop()

    def get_detections(self, focus_cam_id: str | None = None) -> dict[str, Any]:
        if focus_cam_id is not None:
            self._detector.set_focus(focus_cam_id or None)
        return self._detector.get_all()

    def set_focus(self, cam_id: str | None) -> dict[str, Any]:
        if cam_id:
            self._camera_service.get_camera(cam_id)
        self._detector.set_focus(cam_id or None)
        return {"focus_cam_id": cam_id or None}

    def reset_stats(self, cam_id: str) -> dict[str, Any]:
        self._camera_service.get_camera(cam_id)
        return self._detector.reset_stats(cam_id)
