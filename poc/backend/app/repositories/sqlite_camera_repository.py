"""SQLite implementation of CameraRepository with one-time JSON migration."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.sqlite_store import SqliteStore
from app.repositories.camera_repository import DEFAULT_CAMERAS

logger = get_logger("app.repositories.sqlite_camera_repository")


class SqliteCameraRepository:
    """Thread-safe SQLite repository implementing CameraRepository Protocol."""

    def __init__(self, store: SqliteStore, legacy_json_file: Path | None = None) -> None:
        self._store = store
        self._legacy_json_file = legacy_json_file
        self._lock = threading.Lock()
        self._migrate_if_needed()

    def _migrate_if_needed(self) -> None:
        with self._lock:
            with self._store.engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM cameras")).scalar_one()
            if count > 0:
                return

            seed_cameras: list[dict[str, Any]] = [dict(c) for c in DEFAULT_CAMERAS]
            migrated_from_json = False
            if self._legacy_json_file is not None and self._legacy_json_file.is_file():
                try:
                    raw = json.loads(self._legacy_json_file.read_text(encoding="utf-8"))
                    if isinstance(raw, list) and raw:
                        seed_cameras = raw
                        migrated_from_json = True
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning("Failed reading legacy cameras.json for migration: %s", exc)

            self._write_unlocked(seed_cameras)
            if migrated_from_json and self._legacy_json_file is not None:
                backup_path = self._legacy_json_file.with_name(f"{self._legacy_json_file.name}.migrated")
                try:
                    self._legacy_json_file.rename(backup_path)
                    logger.info("Migrated cameras.json -> SQLite (%s)", backup_path.name)
                except OSError as exc:
                    logger.warning("Could not rename cameras.json after migration: %s", exc)

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            with self._store.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, channel, name, zone_name, note, subtype, mode, "
                        "feature_type, grace_seconds, warning_seconds, enabled, zone_json "
                        "FROM cameras ORDER BY sort_order ASC, channel ASC"
                    )
                ).mappings().all()
            cameras: list[dict[str, Any]] = []
            for r in rows:
                try:
                    zone = json.loads(r["zone_json"] or "[]")
                except json.JSONDecodeError:
                    zone = []
                cameras.append(
                    {
                        "id": str(r["id"]),
                        "channel": int(r["channel"]),
                        "name": str(r["name"]),
                        "zone_name": str(r["zone_name"] or ""),
                        "note": str(r["note"] or ""),
                        "subtype": int(r["subtype"]),
                        "mode": str(r["mode"]),
                        "feature_type": str(r["feature_type"]),
                        "grace_seconds": float(r["grace_seconds"]),
                        "warning_seconds": float(r["warning_seconds"]),
                        "enabled": bool(r["enabled"]),
                        "zone": zone if isinstance(zone, list) else [],
                    }
                )
            return cameras

    def get_by_id(self, cam_id: str) -> dict[str, Any] | None:
        for cam in self.list_all():
            if cam.get("id") == cam_id:
                return cam
        return None

    def save_all(self, cameras: list[dict[str, Any]]) -> None:
        with self._lock:
            self._write_unlocked(cameras)

    def _write_unlocked(self, cameras: list[dict[str, Any]]) -> None:
        with self._store.engine.begin() as conn:
            conn.execute(text("DELETE FROM cameras"))
            for idx, cam in enumerate(cameras):
                conn.execute(
                    text(
                        """
                        INSERT INTO cameras (
                            id, channel, name, zone_name, note, subtype, mode,
                            feature_type, grace_seconds, warning_seconds, enabled, zone_json, sort_order
                        ) VALUES (
                            :id, :channel, :name, :zone_name, :note, :subtype, :mode,
                            :feature_type, :grace_seconds, :warning_seconds, :enabled, :zone_json, :sort_order
                        )
                        """
                    ),
                    {
                        "id": str(cam["id"]),
                        "channel": int(cam["channel"]),
                        "name": str(cam["name"]),
                        "zone_name": str(cam.get("zone_name", "")),
                        "note": str(cam.get("note", "")),
                        "subtype": int(cam.get("subtype", 0)),
                        "mode": str(cam.get("mode", "mjpeg")),
                        "feature_type": str(cam.get("feature_type", "zone_presence")),
                        "grace_seconds": float(cam.get("grace_seconds", 2.0)),
                        "warning_seconds": float(cam.get("warning_seconds", 10.0)),
                        "enabled": 1 if cam.get("enabled", True) else 0,
                        "zone_json": json.dumps(cam.get("zone") or [], ensure_ascii=False),
                        "sort_order": idx,
                    },
                )
