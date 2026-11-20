"""Camera configuration repository (JSON PoC store, swappable for DB/MQTT)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Protocol

DEFAULT_CAMERAS: list[dict[str, Any]] = [
    {
        "id": "ch16",
        "channel": 16,
        "name": "Tăng trọng 1",
        "note": "Khu vực máy tăng trọng 1",
        "subtype": 0,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
    {
        "id": "ch17",
        "channel": 17,
        "name": "Tăng trọng 2",
        "note": "Khu vực máy tăng trọng 2",
        "subtype": 0,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
    {
        "id": "ch18",
        "channel": 18,
        "name": "Tăng trọng 3",
        "note": "Khu vực máy tăng trọng 3",
        "subtype": 0,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
    {
        "id": "ch21",
        "channel": 21,
        "name": "Định hình 2",
        "note": "Khu vực định hình 2",
        "subtype": 0,
        "mode": "mjpeg",
        "enabled": True,
        "zone": [],
    },
]


class CameraRepository(Protocol):
    def list_all(self) -> list[dict[str, Any]]: ...
    def get_by_id(self, cam_id: str) -> dict[str, Any] | None: ...
    def save_all(self, cameras: list[dict[str, Any]]) -> None: ...


class JsonCameraRepository:
    """Thread-safe JSON file repository for PoC camera & zone state."""

    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._lock = threading.Lock()

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._data_file.exists():
                self._write_unlocked(DEFAULT_CAMERAS)
                return [dict(c) for c in DEFAULT_CAMERAS]
            try:
                data = json.loads(self._data_file.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except (OSError, json.JSONDecodeError):
                return [dict(c) for c in DEFAULT_CAMERAS]

    def get_by_id(self, cam_id: str) -> dict[str, Any] | None:
        for cam in self.list_all():
            if cam.get("id") == cam_id:
                return cam
        return None

    def save_all(self, cameras: list[dict[str, Any]]) -> None:
        with self._lock:
            self._write_unlocked(cameras)

    def _write_unlocked(self, cameras: list[dict[str, Any]]) -> None:
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        self._data_file.write_text(
            json.dumps(cameras, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
