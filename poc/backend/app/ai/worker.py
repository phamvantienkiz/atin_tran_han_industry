"""Background NVR snapshot AI worker for PoC live view."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np

from app.ai.detector import YoloPersonDetector
from app.ai.rule_engine import ZoneRuleEngine
from app.core.logging import get_logger

logger = get_logger("app.ai.worker")


class PersonZoneDetector:
    """Background CPU worker running YOLO26s person-in-zone detection on NVR snapshots."""

    def __init__(
        self,
        model_path: Path,
        nvr_base_url: str,
        nvr_user: str,
        nvr_pass: str,
        load_cameras_fn: Callable[[], list[dict[str, Any]]],
        conf: float = 0.45,
        imgsz: int = 640,
        interval_sec: float = 0.5,
        focus_interval_sec: float = 0.15,
        focus_ttl_sec: float = 15.0,
        confirm_seconds: float = 2.0,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.nvr_base_url = nvr_base_url
        self.nvr_user = nvr_user
        self.nvr_pass = nvr_pass
        self.load_cameras_fn = load_cameras_fn
        self.interval_sec = interval_sec
        self.focus_interval_sec = focus_interval_sec
        self.focus_ttl_sec = focus_ttl_sec

        self._detector = YoloPersonDetector(model_path=model_path, conf=conf, imgsz=imgsz)
        self._rule_engine = ZoneRuleEngine(
            confirm_seconds=confirm_seconds,
            cooldown_seconds=cooldown_seconds,
        )
        self._lock = threading.Lock()
        self._results: dict[str, dict[str, Any]] = {}
        self._focus_cam_id: str | None = None
        self._focus_updated_at: float = 0.0
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self._detector.model_path.exists():
            logger.warning("YOLO model not found at %s; AI worker disabled.", self._detector.model_path)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="yolo26-zone-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def set_focus(self, cam_id: str | None) -> None:
        with self._lock:
            changed = self._focus_cam_id != cam_id
            self._focus_cam_id = cam_id
            self._focus_updated_at = time.monotonic() if cam_id else 0.0
        if changed:
            self._wake_event.set()

    def _get_active_focus(self) -> str | None:
        with self._lock:
            if not self._focus_cam_id:
                return None
            if (time.monotonic() - self._focus_updated_at) > self.focus_ttl_sec:
                self._focus_cam_id = None
                return None
            return self._focus_cam_id

    def get_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._results)

    def _detect_camera(self, client: httpx.Client, cam: dict[str, Any]) -> dict[str, Any]:
        cam_id = cam["id"]
        zone = cam.get("zone") or []
        has_zone = len(zone) >= 3
        url = f"{self.nvr_base_url}/cgi-bin/snapshot.cgi?channel={cam['channel']}"

        resp = client.get(url)
        if resp.status_code != 200:
            return self._empty_result(cam_id, has_zone, error=f"HTTP {resp.status_code}")

        buf = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            return self._empty_result(cam_id, has_zone, error="Decode failed")

        t0 = time.perf_counter()
        detections = self._detector.detect(frame)
        inference_ms = round((time.perf_counter() - t0) * 1000)

        eval_res = self._rule_engine.evaluate(zone_key=cam_id, detections=detections, polygon=zone)
        return {
            "cam_id": cam_id,
            "has_zone": eval_res.has_zone,
            "person_in_zone": eval_res.person_in_zone,
            "in_zone_count": eval_res.in_zone_count,
            "total_persons": len(eval_res.persons),
            "persons": eval_res.persons,
            "dwell_seconds": eval_res.dwell_seconds,
            "event_triggered": eval_res.should_emit_event,
            "inference_ms": inference_ms,
            "updated_at": time.time(),
        }

    @staticmethod
    def _empty_result(cam_id: str, has_zone: bool, error: str) -> dict[str, Any]:
        return {
            "cam_id": cam_id,
            "has_zone": has_zone,
            "person_in_zone": False,
            "in_zone_count": 0,
            "total_persons": 0,
            "persons": [],
            "error": error,
            "updated_at": time.time(),
        }

    def _run_loop(self) -> None:
        self._detector.ensure_session()
        auth = httpx.DigestAuth(self.nvr_user, self.nvr_pass)
        with httpx.Client(auth=auth, timeout=6.0) as client:
            while not self._stop_event.is_set():
                self._wake_event.clear()
                focus_id = self._get_active_focus()
                all_cameras = [c for c in self.load_cameras_fn() if c.get("enabled", True)]

                if focus_id:
                    cameras = [c for c in all_cameras if c.get("id") == focus_id]
                    wait_sec = self.focus_interval_sec
                else:
                    cameras = [c for c in all_cameras if len(c.get("zone") or []) >= 3]
                    wait_sec = self.interval_sec

                if not cameras:
                    self._wake_event.wait(1.0)
                    continue

                for cam in cameras:
                    if self._stop_event.is_set():
                        break
                    if not focus_id and self._get_active_focus():
                        break
                    try:
                        result = self._detect_camera(client, cam)
                    except Exception as exc:  # noqa: BLE001 - keep worker loop alive across camera errors
                        result = self._empty_result(
                            cam["id"],
                            len(cam.get("zone") or []) >= 3,
                            error=str(exc),
                        )
                    with self._lock:
                        self._results[cam["id"]] = result

                self._wake_event.wait(wait_sec)
