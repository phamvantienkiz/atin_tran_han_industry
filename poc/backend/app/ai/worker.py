"""Background GPU/CPU AI worker integrating NvrStreamManager, YOLO, ByteTrack & ZoneRuleEngine."""

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
from app.ai.nvr_stream import NvrFramePacket, NvrStreamManager
from app.ai.rule_engine import ZoneEvaluation, ZoneRuleEngine
from app.ai.tracker import CameraTracker, TrackedPerson
from app.core.logging import get_logger

logger = get_logger("app.ai.worker")

_TIMER_REFRESH_INTERVAL_SEC = 0.5
_BBOX_STALE_SEC = 1.5


class PersonZoneDetector:
    """Background AI worker running YOLO ONNX + ByteTrack + 4-state ZoneRuleEngine."""

    def __init__(
        self,
        model_path: Path,
        nvr_base_url: str,
        nvr_user: str,
        nvr_pass: str,
        load_cameras_fn: Callable[[], list[dict[str, Any]]],
        conf: float = 0.40,
        imgsz: int = 640,
        interval_sec: float = 0.5,
        focus_interval_sec: float = 0.15,
        focus_ttl_sec: float = 15.0,
        confirm_seconds: float = 2.0,
        cooldown_seconds: float = 60.0,
        runtime: str = "auto",
        vram_limit_mb: int = 1024,
        target_fps: float = 12.0,
        anchor_mode: str = "center",
        grace_seconds: float = 2.0,
        warning_seconds: float = 10.0,
        timeline_window_seconds: int = 1800,
        nvr_stream_manager: NvrStreamManager | None = None,
        on_update: Callable[[dict[str, dict[str, Any]]], None] | None = None,
    ) -> None:
        self.nvr_base_url = nvr_base_url
        self.nvr_user = nvr_user
        self.nvr_pass = nvr_pass
        self.load_cameras_fn = load_cameras_fn
        self.interval_sec = interval_sec
        self.focus_interval_sec = focus_interval_sec
        self.focus_ttl_sec = focus_ttl_sec
        self.target_fps = max(1.0, target_fps)

        self._stream_manager = nvr_stream_manager
        self._on_update = on_update

        self._detector = YoloPersonDetector(
            model_path=model_path,
            conf=conf,
            imgsz=imgsz,
            runtime=runtime,
            vram_limit_mb=vram_limit_mb,
        )
        self._tracker = CameraTracker(frame_rate=max(1, round(self.target_fps)))
        self._rule_engine = ZoneRuleEngine(
            confirm_seconds=confirm_seconds,
            cooldown_seconds=cooldown_seconds,
            grace_seconds=grace_seconds,
            warning_seconds=warning_seconds,
            timeline_window_seconds=timeline_window_seconds,
            anchor_mode=anchor_mode,
            default_feature_type="zone_presence",
        )

        self._lock = threading.Lock()
        self._results: dict[str, dict[str, Any]] = {}
        self._last_seq: dict[str, int] = {}
        self._last_tracked: dict[str, list[TrackedPerson]] = {}
        self._last_infer_mono: dict[str, float] = {}
        self._last_timer_tick: dict[str, float] = {}
        self._focus_cam_id: str | None = None
        self._focus_updated_at: float = 0.0
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def active_provider(self) -> str:
        return self._detector.active_provider

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

    def reset_stats(self, cam_id: str) -> dict[str, Any]:
        """Reset rule engine counters, timeline, and tracker state for one camera."""
        with self._lock:
            self._rule_engine.reset_stats(cam_id)
            self._tracker.reset(cam_id)
            self._last_tracked.pop(cam_id, None)
            self._last_timer_tick.pop(cam_id, None)
            self._results.pop(cam_id, None)
            snapshot = dict(self._results)
        self._notify_update(snapshot)
        return {"status": "reset", "cam_id": cam_id}

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

    def _notify_update(self, snapshot: dict[str, dict[str, Any]]) -> None:
        if self._on_update is not None:
            try:
                self._on_update(snapshot)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Detection update callback failed: %s", exc)

    def _build_result(
        self,
        cam_id: str,
        eval_res: ZoneEvaluation,
        inference_ms: int,
        updated_at: float | None = None,
    ) -> dict[str, Any]:
        return {
            "cam_id": cam_id,
            "has_zone": eval_res.has_zone,
            "person_in_zone": eval_res.person_in_zone,
            "in_zone_count": eval_res.in_zone_count,
            "total_persons": len(eval_res.persons),
            "persons": eval_res.persons,
            "dwell_seconds": eval_res.dwell_seconds,
            "event_triggered": eval_res.should_emit_event,
            "status": eval_res.status,
            "ui_color": eval_res.ui_color,
            "status_label": eval_res.status_label,
            "sub_label": eval_res.sub_label,
            "polygon_label": eval_res.polygon_label,
            "empty_duration": eval_res.empty_duration,
            "alert_count": eval_res.alert_count,
            "total_alert_seconds": eval_res.total_alert_seconds,
            "session_duration_seconds": eval_res.session_duration_seconds,
            "timeline": eval_res.timeline,
            "inference_ms": inference_ms,
            "active_provider": self._detector.active_provider,
            "updated_at": time.time() if updated_at is None else updated_at,
        }

    def _evaluate_camera(
        self,
        cam: dict[str, Any],
        tracked: list[TrackedPerson],
        inference_ms: int,
        updated_at: float | None = None,
    ) -> dict[str, Any]:
        cam_id = str(cam["id"])
        zone = cam.get("zone") or []
        zone_name = str(cam.get("zone_name") or cam.get("name") or "")
        feature_type = str(cam.get("feature_type") or "zone_presence")
        grace_raw = cam.get("grace_seconds")
        warning_raw = cam.get("warning_seconds")

        eval_res = self._rule_engine.evaluate(
            zone_key=cam_id,
            detections=tracked,
            polygon=zone,
            feature_type=feature_type,
            zone_name=zone_name,
            grace_seconds=float(grace_raw) if grace_raw is not None else None,
            warning_seconds=float(warning_raw) if warning_raw is not None else None,
        )
        return self._build_result(cam_id, eval_res, inference_ms=inference_ms, updated_at=updated_at)

    def _detect_camera(self, client: httpx.Client, cam: dict[str, Any]) -> dict[str, Any]:
        """Fallback single-camera snapshot inference when NvrStreamManager is unavailable."""
        cam_id = str(cam["id"])
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
        raw_dets = self._detector.detect(frame)
        inference_ms = round((time.perf_counter() - t0) * 1000)

        tracked = self._tracker.update(cam_id, raw_dets)
        now_mono = time.monotonic()
        self._last_tracked[cam_id] = tracked
        self._last_infer_mono[cam_id] = now_mono
        self._last_timer_tick[cam_id] = now_mono
        return self._evaluate_camera(cam, tracked, inference_ms=inference_ms)

    @staticmethod
    def _empty_result(cam_id: str, has_zone: bool, error: str) -> dict[str, Any]:
        return {
            "cam_id": cam_id,
            "has_zone": has_zone,
            "person_in_zone": False,
            "in_zone_count": 0,
            "total_persons": 0,
            "persons": [],
            "status": "idle" if not has_zone else "empty",
            "ui_color": "idle" if not has_zone else "yellow",
            "status_label": "CHƯA VẼ VÙNG" if not has_zone else "VÙNG TRỐNG",
            "sub_label": error,
            "polygon_label": "",
            "empty_duration": 0.0,
            "alert_count": 0,
            "total_alert_seconds": 0.0,
            "session_duration_seconds": 0.0,
            "timeline": [],
            "error": error,
            "updated_at": time.time(),
        }

    def _run_stream_cycle(self, all_cameras: list[dict[str, Any]]) -> bool:
        assert self._stream_manager is not None
        self._stream_manager.sync_cameras(all_cameras)

        focus_id = self._get_active_focus()
        if focus_id:
            target_cams = [c for c in all_cameras if c.get("id") == focus_id]
        else:
            target_cams = all_cameras

        ready_cams: list[dict[str, Any]] = []
        ready_packets: list[NvrFramePacket] = []
        idle_cams: list[dict[str, Any]] = []

        for cam in target_cams:
            cam_id = str(cam["id"])
            pkt = self._stream_manager.latest(cam_id)
            if pkt is not None and pkt.seq != self._last_seq.get(cam_id):
                ready_cams.append(cam)
                ready_packets.append(pkt)
            else:
                idle_cams.append(cam)

        changed = False
        now_mono = time.monotonic()

        if ready_cams:
            t0 = time.perf_counter()
            batch_dets = self._detector.detect_batch([p.frame for p in ready_packets])
            total_ms = (time.perf_counter() - t0) * 1000.0
            per_cam_ms = max(1, round(total_ms / len(ready_cams)))

            for cam, pkt, raw_dets in zip(ready_cams, ready_packets, batch_dets):
                cam_id = str(cam["id"])
                tracked = self._tracker.update(cam_id, raw_dets)
                result = self._evaluate_camera(cam, tracked, inference_ms=per_cam_ms, updated_at=pkt.ts_wall)
                with self._lock:
                    self._results[cam_id] = result
                    self._last_seq[cam_id] = pkt.seq
                    self._last_tracked[cam_id] = tracked
                    self._last_infer_mono[cam_id] = now_mono
                    self._last_timer_tick[cam_id] = now_mono
                changed = True

        # Keep HUD clocks ticking smoothly even between new frames
        for cam in idle_cams:
            cam_id = str(cam["id"])
            last_tick = self._last_timer_tick.get(cam_id, 0.0)
            if (now_mono - last_tick) < _TIMER_REFRESH_INTERVAL_SEC:
                continue
            with self._lock:
                prev_result = self._results.get(cam_id)
                last_infer = self._last_infer_mono.get(cam_id, 0.0)
                last_tracked = list(self._last_tracked.get(cam_id, []))
            if prev_result is None and len(cam.get("zone") or []) < 3:
                continue

            is_stale = (now_mono - last_infer) > _BBOX_STALE_SEC
            effective_tracked = [] if is_stale else last_tracked
            prev_ms = int(prev_result.get("inference_ms", 0)) if prev_result else 0
            # Keep previous updated_at if frame is stale so frontend anti-ghosting remains accurate
            prev_updated = float(prev_result.get("updated_at", time.time())) if prev_result else time.time()
            result = self._evaluate_camera(
                cam,
                effective_tracked,
                inference_ms=prev_ms,
                updated_at=prev_updated if is_stale else time.time(),
            )
            with self._lock:
                self._results[cam_id] = result
                self._last_timer_tick[cam_id] = now_mono
            changed = True

        return changed

    def _run_loop(self) -> None:
        self._detector.ensure_session()
        auth = httpx.DigestAuth(self.nvr_user, self.nvr_pass)
        tick_interval = 1.0 / self.target_fps

        with httpx.Client(auth=auth, timeout=6.0) as client:
            while not self._stop_event.is_set():
                loop_start = time.monotonic()
                self._wake_event.clear()

                try:
                    all_cameras = [c for c in self.load_cameras_fn() if c.get("enabled", True)]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to load cameras in AI loop: %s", exc)
                    self._wake_event.wait(1.0)
                    continue

                if self._stream_manager is not None:
                    try:
                        changed = self._run_stream_cycle(all_cameras)
                    except Exception:
                        logger.exception("Error in AI stream cycle")
                        changed = False

                    if changed:
                        self._notify_update(self.get_all())

                    elapsed = time.monotonic() - loop_start
                    wait_sec = max(0.01, tick_interval - elapsed)
                    self._wake_event.wait(wait_sec)
                    continue

                # Legacy snapshot fallback path when NvrStreamManager is not attached
                focus_id = self._get_active_focus()
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
                    except Exception as exc:  # noqa: BLE001
                        result = self._empty_result(
                            str(cam["id"]),
                            len(cam.get("zone") or []) >= 3,
                            error=str(exc),
                        )
                    with self._lock:
                        self._results[str(cam["id"])] = result
                self._notify_update(self.get_all())
                self._wake_event.wait(wait_sec)
