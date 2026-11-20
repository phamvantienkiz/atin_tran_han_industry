"""Background GPU/CPU AI worker integrating NvrStreamManager, DecodePool, YOLO, ByteTrack & RuleEngine."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np

from app.ai.detector import YoloPersonDetector
from app.ai.display_pipeline import DisplayAndSyncPipeline
from app.ai.nvr_stream import NvrFramePacket, NvrStreamManager
from app.ai.rule_engine import ZoneEvaluation, ZoneRuleEngine
from app.ai.tracker import CameraTracker, TrackedPerson
from app.core.logging import get_logger
from app.db.sqlite_store import SqliteStore

logger = get_logger("app.ai.worker")

_HUD_EMIT_INTERVAL_SEC = 1.0
_TIMELINE_EMIT_INTERVAL_SEC = 2.0
_SNAPSHOT_SAVE_INTERVAL_SEC = 12.0
_METRICS_LOG_INTERVAL_SEC = 10.0


class PersonZoneDetector:
    """Background AI worker running YOLO ONNX (S1) + ByteTrack + 4-state ZoneRuleEngine."""

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
        vram_limit_mb: int = 1536,
        target_fps: float = 0.0,
        snap_min_iou: float = 0.25,
        decode_reduce: int = 1,
        anchor_mode: str = "bottom_center",
        grace_seconds: float = 2.0,
        warning_seconds: float = 10.0,
        timeline_window_seconds: int = 1800,
        nvr_stream_manager: NvrStreamManager | None = None,
        display_pipeline: DisplayAndSyncPipeline | None = None,
        sqlite_store: SqliteStore | None = None,
        ws_legacy_payload: bool = False,
        on_update: Callable[[dict[str, dict[str, Any]]], None] | None = None,
        on_bbox: Callable[[dict[str, Any]], None] | None = None,
        on_hud: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.nvr_base_url = nvr_base_url
        self.nvr_user = nvr_user
        self.nvr_pass = nvr_pass
        self.load_cameras_fn = load_cameras_fn
        self.interval_sec = interval_sec
        self.focus_interval_sec = focus_interval_sec
        self.focus_ttl_sec = focus_ttl_sec
        self.target_fps = max(0.0, target_fps)
        self.decode_reduce = 2 if decode_reduce == 2 else 1
        self.ws_legacy_payload = ws_legacy_payload
        self._prefetch_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-prefetch")

        self._stream_manager = nvr_stream_manager
        self._display_pipeline = display_pipeline
        self._sqlite_store = sqlite_store
        self._on_update = on_update
        self._on_bbox = on_bbox
        self._on_hud = on_hud

        self._detector = YoloPersonDetector(
            model_path=model_path,
            conf=conf,
            imgsz=imgsz,
            runtime=runtime,
            vram_limit_mb=vram_limit_mb,
        )
        self._tracker = CameraTracker(frame_rate=6, snap_min_iou=snap_min_iou)
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
        self._last_frame_id: dict[str, int] = {}
        self._last_hud_emit_mono: dict[str, float] = {}
        self._last_timeline_emit_mono: dict[str, float] = {}
        self._last_hud_status: dict[str, str] = {}
        self._alert_started_wall: dict[str, float] = {}
        self._ai_metrics: dict[str, dict[str, Any]] = {}
        self._last_snapshot_save_mono: float = 0.0
        self._last_metrics_log_mono: float = 0.0

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
        if self._sqlite_store is not None:
            try:
                recent = self._sqlite_store.load_recent_snapshots(max_age_sec=1800.0)
                if recent:
                    self._rule_engine.restore_snapshots(recent)
                    logger.info("Restored %d camera runtime snapshots from SQLite", len(recent))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed restoring SQLite runtime snapshots: %s", exc)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="yolo26-zone-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._prefetch_pool.shutdown(wait=False, cancel_futures=True)
        if self._sqlite_store is not None:
            try:
                snaps = self._rule_engine.export_snapshots()
                self._sqlite_store.enqueue_runtime_snapshots(snaps)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed saving runtime snapshots on stop: %s", exc)

    def set_focus(self, cam_id: str | None) -> None:
        with self._lock:
            changed = self._focus_cam_id != cam_id
            self._focus_cam_id = cam_id
            self._focus_updated_at = time.monotonic() if cam_id else 0.0
        if changed:
            self._wake_event.set()

    def notify_new_frame(self) -> None:
        """Wake AI worker when a new NVR frame arrives."""
        self._wake_event.set()

    def reset_stats(self, cam_id: str) -> dict[str, Any]:
        """Reset rule engine counters, timeline, and tracker state for one camera."""
        with self._lock:
            self._rule_engine.reset_stats(cam_id)
            self._tracker.reset(cam_id)
            self._last_hud_emit_mono.pop(cam_id, None)
            self._last_timeline_emit_mono.pop(cam_id, None)
            self._last_hud_status.pop(cam_id, None)
            self._alert_started_wall.pop(cam_id, None)
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

    def get_metrics(self) -> dict[str, Any]:
        display_metrics = self._display_pipeline.get_metrics() if self._display_pipeline else {}
        with self._lock:
            ai_m = {k: dict(v) for k, v in self._ai_metrics.items()}
        merged: dict[str, dict[str, Any]] = {}
        for cam_id in sorted(set(display_metrics.keys()) | set(ai_m.keys())):
            merged[cam_id] = {**display_metrics.get(cam_id, {}), **ai_m.get(cam_id, {})}
        return {
            "active_provider": self._detector.active_provider,
            "cameras": merged,
        }

    def _notify_update(self, snapshot: dict[str, dict[str, Any]]) -> None:
        if self._on_update is not None and self.ws_legacy_payload:
            try:
                self._on_update(snapshot)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Detection update callback failed: %s", exc)

    def _emit_hud_if_needed(self, cam_id: str, result: dict[str, Any], now_mono: float) -> None:
        if self._on_hud is None:
            return
        prev_status = self._last_hud_status.get(cam_id)
        last_emit = self._last_hud_emit_mono.get(cam_id, 0.0)
        status_changed = prev_status != result["status"]
        if not status_changed and (now_mono - last_emit) < _HUD_EMIT_INTERVAL_SEC:
            return

        self._last_hud_status[cam_id] = result["status"]
        self._last_hud_emit_mono[cam_id] = now_mono

        include_timeline = status_changed or (
            now_mono - self._last_timeline_emit_mono.get(cam_id, 0.0)
        ) >= _TIMELINE_EMIT_INTERVAL_SEC
        if include_timeline:
            self._last_timeline_emit_mono[cam_id] = now_mono

        hud_msg: dict[str, Any] = {
            "type": "hud",
            "cam_id": cam_id,
            "has_zone": result["has_zone"],
            "status": result["status"],
            "ui_color": result["ui_color"],
            "status_label": result["status_label"],
            "sub_label": result["sub_label"],
            "polygon_label": result["polygon_label"],
            "alert_count": result["alert_count"],
            "total_alert_seconds": result["total_alert_seconds"],
            "session_duration_seconds": result["session_duration_seconds"],
            "in_zone_count": result["in_zone_count"],
            "active_provider": result["active_provider"],
        }
        if include_timeline:
            hud_msg["timeline"] = result["timeline"]

        try:
            self._on_hud(hud_msg)
        except Exception as exc:  # noqa: BLE001
            logger.debug("on_hud callback failed: %s", exc)

    def _track_alert_events(self, cam_id: str, new_status: str) -> None:
        if self._sqlite_store is None:
            return
        now_wall = time.time()
        started = self._alert_started_wall.get(cam_id)
        if new_status == "alert" and started is None:
            self._alert_started_wall[cam_id] = now_wall
        elif new_status != "alert" and started is not None:
            self._alert_started_wall.pop(cam_id, None)
            self._sqlite_store.enqueue_alert_event(
                cam_id=cam_id,
                started_at=started,
                ended_at=now_wall,
                duration_s=round(max(0.0, now_wall - started), 2),
                peak_state="alert",
            )

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
        self._track_alert_events(cam_id, eval_res.status)
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

    def _fetch_and_prepare(
        self,
        cam: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        NvrFramePacket | None,
        tuple[np.ndarray, int, int, float, float, float] | None,
        float,
    ]:
        """Just-In-Time fetch latest frame for one camera, decode & preprocess off the GPU thread."""
        assert self._stream_manager is not None
        cam_id = str(cam["id"])
        pkt = self._stream_manager.latest(cam_id)
        if pkt is None or pkt.seq == self._last_frame_id.get(cam_id):
            return cam, None, None, 0.0

        t_dec = time.perf_counter()
        if pkt.frame is not None:
            bgr = pkt.frame
        else:
            flag = cv2.IMREAD_REDUCED_COLOR_2 if self.decode_reduce == 2 else cv2.IMREAD_COLOR
            buf = np.frombuffer(pkt.jpeg_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(buf, flag)
        if bgr is None:
            return cam, pkt, None, round((time.perf_counter() - t_dec) * 1000.0, 2)

        prepped = self._detector.preprocess_frame(bgr)
        prep_ms = round((time.perf_counter() - t_dec) * 1000.0, 2)
        return cam, pkt, prepped, prep_ms

    def _run_stream_cycle(self, all_cameras: list[dict[str, Any]]) -> bool:
        assert self._stream_manager is not None
        self._stream_manager.sync_cameras(all_cameras)
        if self._display_pipeline is not None:
            self._display_pipeline.update_zones(all_cameras)

        focus_id = self._get_active_focus()
        if focus_id:
            target_cams = [c for c in all_cameras if c.get("id") == focus_id]
        else:
            # Skip AI on cameras without a zone to save GPU cycles
            target_cams = [c for c in all_cameras if len(c.get("zone") or []) >= 3]

        idle_cams: list[dict[str, Any]] = []
        changed = False
        now_mono = time.monotonic()

        # Single-pass JIT fetch + 1-cam overlap prefetch:
        # While GPU runs Cam i, prefetch thread decodes & preprocesses latest frame of Cam i+1.
        next_fut: Future[Any] | None = None
        for idx, cam in enumerate(target_cams):
            if self._stop_event.is_set():
                break

            if next_fut is not None:
                cam_cur, pkt, prepped, prep_ms = next_fut.result()
                next_fut = None
            else:
                cam_cur, pkt, prepped, prep_ms = self._fetch_and_prepare(cam)

            cam_id = str(cam_cur["id"])
            if pkt is None:
                idle_cams.append(cam_cur)
                continue
            if prepped is None:
                with self._lock:
                    self._last_frame_id[cam_id] = pkt.seq
                continue

            # Overlap: start JIT fetch+decode+preprocess of Cam i+1 while GPU runs Cam i
            if idx + 1 < len(target_cams) and not self._stop_event.is_set():
                next_fut = self._prefetch_pool.submit(self._fetch_and_prepare, target_cams[idx + 1])

            blob, orig_w, orig_h, scale, pad_x, pad_y = prepped
            t_inf = time.perf_counter()
            raw_dets = self._detector.infer_preprocessed(blob, orig_w, orig_h, scale, pad_x, pad_y)
            infer_ms = max(1, round((time.perf_counter() - t_inf) * 1000.0))

            t_trk = time.perf_counter()
            tracked = self._tracker.update(cam_id, raw_dets, ts_mono=pkt.ts_mono)
            track_ms = round((time.perf_counter() - t_trk) * 1000.0, 2)

            result = self._evaluate_camera(cam_cur, tracked, inference_ms=infer_ms, updated_at=pkt.ts_wall)
            e2e_ms = round((time.monotonic() - pkt.ts_mono) * 1000.0)
            with self._lock:
                self._results[cam_id] = result
                self._last_frame_id[cam_id] = pkt.seq
                self._ai_metrics[cam_id] = {
                    "decode_prep_ms": prep_ms,
                    "infer_ms": infer_ms,
                    "track_ms": track_ms,
                    "e2e_ms": e2e_ms,
                }

            if self._on_bbox is not None:
                self._on_bbox(
                    {
                        "type": "bbox",
                        "cam_id": cam_id,
                        "frame_id": pkt.seq,
                        "ts_capture": pkt.ts_wall,
                        "delay_ms": e2e_ms,
                        "inference_ms": infer_ms,
                        "in_zone_count": result["in_zone_count"],
                        "persons": result["persons"],
                    }
                )

            self._emit_hud_if_needed(cam_id, result, time.monotonic())
            changed = True

        # Update HUD clocks only (NEVER re-emit stale BBoxes!)
        for cam in idle_cams:
            cam_id = str(cam["id"])
            last_hud = self._last_hud_emit_mono.get(cam_id, 0.0)
            if (now_mono - last_hud) < _HUD_EMIT_INTERVAL_SEC:
                continue
            with self._lock:
                prev_result = self._results.get(cam_id)
            if prev_result is None:
                continue
            # Evaluate rule engine with empty_if_no_infer? No, only advance timer using previous in_zone_count
            # by passing synthetic anchor or keeping previous status timer via evaluate([] if empty else keep)
            prev_in_zone = int(prev_result.get("in_zone_count", 0))
            if prev_in_zone == 0:
                result = self._evaluate_camera(
                    cam,
                    [],
                    inference_ms=int(prev_result.get("inference_ms", 0)),
                    updated_at=float(prev_result.get("updated_at", time.time())),
                )
                with self._lock:
                    self._results[cam_id] = result
                self._emit_hud_if_needed(cam_id, result, now_mono)
                changed = True

        # Periodic SQLite snapshot & metrics logging
        if self._sqlite_store is not None and (now_mono - self._last_snapshot_save_mono) >= _SNAPSHOT_SAVE_INTERVAL_SEC:
            self._last_snapshot_save_mono = now_mono
            self._sqlite_store.enqueue_runtime_snapshots(self._rule_engine.export_snapshots())

        if (now_mono - self._last_metrics_log_mono) >= _METRICS_LOG_INTERVAL_SEC:
            self._last_metrics_log_mono = now_mono
            logger.info("METRICS %s", self.get_metrics())

        return changed

    def _run_loop(self) -> None:
        self._detector.ensure_session()
        auth = httpx.DigestAuth(self.nvr_user, self.nvr_pass)
        tick_interval = (1.0 / self.target_fps) if self.target_fps > 0 else 0.0

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

                    if tick_interval > 0:
                        elapsed = time.monotonic() - loop_start
                        wait_sec = max(0.005, tick_interval - elapsed)
                        self._wake_event.wait(wait_sec)
                    elif self._display_pipeline is not None:
                        self._display_pipeline.wait_for_ai_work(timeout=0.05)
                    else:
                        self._wake_event.wait(0.02)
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
