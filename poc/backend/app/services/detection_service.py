"""Detection orchestration service."""

from __future__ import annotations

from typing import Any

from app.ai.worker import PersonZoneDetector
from app.db.sqlite_store import SqliteStore
from app.services.camera_service import CameraService


class DetectionService:
    """Exposes live AI detections, focus control, stats reset, metrics, and alert history."""

    def __init__(
        self,
        detector: PersonZoneDetector,
        camera_service: CameraService,
        sqlite_store: SqliteStore | None = None,
    ) -> None:
        self._detector = detector
        self._camera_service = camera_service
        self._sqlite_store = sqlite_store

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

    def get_metrics(self) -> dict[str, Any]:
        return self._detector.get_metrics()

    def query_alert_events(
        self,
        cam_id: str,
        from_ts: float | None = None,
        to_ts: float | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self._camera_service.get_camera(cam_id)
        if self._sqlite_store is None:
            return []
        return self._sqlite_store.query_alert_events(cam_id, from_ts=from_ts, to_ts=to_ts, limit=limit)
