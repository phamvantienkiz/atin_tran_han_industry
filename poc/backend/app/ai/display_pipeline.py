"""Shared DecodePool, two-tier display JPEG encoder, and Time-Aligned Delayed Playback."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.ai.nvr_stream import NvrFramePacket
from app.ai.tracker import TrackedPerson
from app.core.logging import get_logger
from app.utils.geometry import point_in_polygon

logger = get_logger("app.ai.display_pipeline")


@dataclass
class DecodedFrame:
    """Single full-res decoded frame shared by AI Core and all MJPEG viewers."""

    cam_id: str
    frame_id: int
    ts_mono: float
    ts_wall: float
    bgr: np.ndarray
    decode_ms: float
    _enc_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _grid_jpeg: bytes | None = None
    _focus_jpeg: bytes | None = None

    def get_encoded_jpeg(
        self,
        view: str,
        grid_w: int,
        grid_q: int,
        focus_w: int,
        focus_q: int,
    ) -> tuple[bytes, float]:
        """Encode once per tier (grid or focus) and cache for all concurrent viewers."""
        is_focus = view == "focus"
        with self._enc_lock:
            cached = self._focus_jpeg if is_focus else self._grid_jpeg
            if cached is not None:
                return cached, 0.0

            t0 = time.perf_counter()
            target_w = focus_w if is_focus else grid_w
            quality = focus_q if is_focus else grid_q
            h, w = self.bgr.shape[:2]
            if target_w > 0 and w > target_w:
                new_h = max(2, round(h * (target_w / w)))
                resized = cv2.resize(self.bgr, (target_w, new_h), interpolation=cv2.INTER_AREA)
            else:
                resized = self.bgr

            ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
            enc_ms = (time.perf_counter() - t0) * 1000.0
            jpg_bytes = buf.tobytes() if ok else b""
            if is_focus:
                self._focus_jpeg = jpg_bytes
            else:
                self._grid_jpeg = jpg_bytes
            return jpg_bytes, enc_ms


@dataclass(frozen=True)
class AiTrackSnapshot:
    ts_mono: float
    tracks: list[TrackedPerson]
    inference_ms: int


def _interpolate_tracks(
    history: list[AiTrackSnapshot],
    target_ts: float,
    max_extrapolate_sec: float = 0.45,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Interpolate or velocity-extrapolate tracks at target_ts. Returns (persons, infer_ms, extrapolated)."""
    if not history:
        return [], 0, False

    prev_snap: AiTrackSnapshot | None = None
    next_snap: AiTrackSnapshot | None = None
    for snap in history:
        if snap.ts_mono <= target_ts:
            prev_snap = snap
        else:
            next_snap = snap
            break

    if prev_snap is None:
        # target_ts is older than oldest AI snapshot; use oldest if close
        oldest = history[0]
        if (oldest.ts_mono - target_ts) <= max_extrapolate_sec:
            return [_track_to_dict(t, predicted=True) for t in oldest.tracks], oldest.inference_ms, True
        return [], oldest.inference_ms, False

    if next_snap is not None and next_snap.ts_mono > prev_snap.ts_mono:
        alpha = (target_ts - prev_snap.ts_mono) / (next_snap.ts_mono - prev_snap.ts_mono)
        alpha = max(0.0, min(1.0, alpha))
        next_by_id = {t.track_id: t for t in next_snap.tracks}
        dt_from_prev = target_ts - prev_snap.ts_mono

        out: list[dict[str, Any]] = []
        for t0 in prev_snap.tracks:
            t1 = next_by_id.get(t0.track_id)
            if t1 is not None:
                x1 = t0.x1 + (t1.x1 - t0.x1) * alpha
                y1 = t0.y1 + (t1.y1 - t0.y1) * alpha
                x2 = t0.x2 + (t1.x2 - t0.x2) * alpha
                y2 = t0.y2 + (t1.y2 - t0.y2) * alpha
                cx = round((x1 + x2) * 0.5, 4)
                cy = round((y1 + y2) * 0.5, 4)
                out.append(
                    {
                        "id": t0.track_id,
                        "track_id": t0.track_id,
                        "x1": round(x1, 4),
                        "y1": round(y1, 4),
                        "x2": round(x2, 4),
                        "y2": round(y2, 4),
                        "cx": cx,
                        "cy": cy,
                        "foot_x": cx,
                        "foot_y": round(y2, 4),
                        "conf": t1.conf,
                        "predicted": bool(t0.predicted or t1.predicted),
                    }
                )
            elif dt_from_prev <= 0.25:
                out.append(_extrapolate_track(t0, dt_from_prev))
        return out, next_snap.inference_ms, False

    dt = target_ts - prev_snap.ts_mono
    if dt <= 0.02:
        return [_track_to_dict(t, predicted=t.predicted) for t in prev_snap.tracks], prev_snap.inference_ms, False
    if dt <= max_extrapolate_sec:
        return [_extrapolate_track(t, dt) for t in prev_snap.tracks], prev_snap.inference_ms, True
    return [], prev_snap.inference_ms, False


def _track_to_dict(t: TrackedPerson, *, predicted: bool) -> dict[str, Any]:
    return {
        "id": t.track_id,
        "track_id": t.track_id,
        "x1": t.x1,
        "y1": t.y1,
        "x2": t.x2,
        "y2": t.y2,
        "cx": t.cx,
        "cy": t.cy,
        "foot_x": t.foot_x,
        "foot_y": t.foot_y,
        "conf": t.conf,
        "predicted": predicted,
    }


def _extrapolate_track(t: TrackedPerson, dt: float) -> dict[str, Any]:
    dx = max(-0.15, min(0.15, t.vx * dt))
    dy = max(-0.15, min(0.15, t.vy * dt))
    x1 = max(0.0, min(1.0, t.x1 + dx))
    y1 = max(0.0, min(1.0, t.y1 + dy))
    x2 = max(0.0, min(1.0, t.x2 + dx))
    y2 = max(0.0, min(1.0, t.y2 + dy))
    cx = round((x1 + x2) * 0.5, 4)
    cy = round((y1 + y2) * 0.5, 4)
    return {
        "id": t.track_id,
        "track_id": t.track_id,
        "x1": round(x1, 4),
        "y1": round(y1, 4),
        "x2": round(x2, 4),
        "y2": round(y2, 4),
        "cx": cx,
        "cy": cy,
        "foot_x": cx,
        "foot_y": round(y2, 4),
        "conf": t.conf,
        "predicted": True,
    }


class DisplayAndSyncPipeline:
    """Manages parallel DecodePool, per-camera ring buffers, and Time-Aligned Delayed Playback."""

    def __init__(
        self,
        *,
        grid_w: int = 960,
        grid_q: int = 80,
        focus_w: int = 1920,
        focus_q: int = 85,
        sync_delay_ms: int = 450,
        valve_ms: int = 150,
        anchor_mode: str = "bottom_center",
        on_bbox_ready: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.grid_w = grid_w
        self.grid_q = grid_q
        self.focus_w = focus_w
        self.focus_q = focus_q
        self.sync_delay_sec = max(0.0, sync_delay_ms / 1000.0)
        self.valve_sec = max(0.05, valve_ms / 1000.0)
        self.anchor_mode = anchor_mode
        self._on_bbox_ready = on_bbox_ready

        self._decode_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="decode-pool")
        self._lock = threading.Lock()
        self._ring: dict[str, deque[DecodedFrame]] = {}
        self._latest_decoded: dict[str, DecodedFrame] = {}
        self._released: dict[str, DecodedFrame] = {}
        self._ai_history: dict[str, deque[AiTrackSnapshot]] = {}
        self._zones: dict[str, list[dict[str, float]]] = {}
        self._last_released_id: dict[str, int] = {}

        # Asyncio event subscribers per cam_id for zero-polling MJPEG delivery
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mjpeg_waiters: dict[str, set[asyncio.Event]] = {}
        self._ai_wake_event = threading.Event()

        # Metrics per camera
        self._metrics: dict[str, dict[str, Any]] = {}
        self._in_timestamps: dict[str, deque[float]] = {}

        self._stop_event = threading.Event()
        self._pacer_thread: threading.Thread | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    def start(self) -> None:
        if self._pacer_thread and self._pacer_thread.is_alive():
            return
        self._stop_event.clear()
        self._pacer_thread = threading.Thread(
            target=self._pacer_loop,
            name="sync-playback-pacer",
            daemon=True,
        )
        self._pacer_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._ai_wake_event.set()
        if self._pacer_thread and self._pacer_thread.is_alive():
            self._pacer_thread.join(timeout=2.0)
        self._decode_pool.shutdown(wait=False, cancel_futures=True)

    def update_zones(self, cameras: list[dict[str, Any]]) -> None:
        with self._lock:
            for cam in cameras:
                self._zones[str(cam["id"])] = list(cam.get("zone") or [])

    def submit_raw_packet(self, pkt: NvrFramePacket) -> None:
        """Called by NvrChannelReader thread when a raw JPEG arrives."""
        if self._stop_event.is_set():
            return
        self._decode_pool.submit(self._decode_and_enqueue, pkt)

    def _decode_and_enqueue(self, pkt: NvrFramePacket) -> None:
        t0 = time.perf_counter()
        arr = np.frombuffer(pkt.jpeg_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return
        decode_ms = (time.perf_counter() - t0) * 1000.0

        df = DecodedFrame(
            cam_id=pkt.cam_id,
            frame_id=pkt.seq,
            ts_mono=pkt.ts_mono,
            ts_wall=pkt.ts_wall,
            bgr=bgr,
            decode_ms=decode_ms,
        )

        with self._lock:
            ring = self._ring.setdefault(pkt.cam_id, deque(maxlen=20))
            if len(ring) == ring.maxlen:
                m = self._metrics.setdefault(pkt.cam_id, {})
                m["dropped_frames"] = int(m.get("dropped_frames", 0)) + 1
            ring.append(df)
            self._latest_decoded[pkt.cam_id] = df

            ts_q = self._in_timestamps.setdefault(pkt.cam_id, deque(maxlen=30))
            ts_q.append(pkt.ts_mono)
            fps_in = 0.0
            if len(ts_q) >= 2:
                span = ts_q[-1] - ts_q[0]
                if span > 0:
                    fps_in = (len(ts_q) - 1) / span
            m = self._metrics.setdefault(pkt.cam_id, {})
            m["fps_in"] = round(fps_in, 2)
            m["decode_ms"] = round(decode_ms, 2)

        self._ai_wake_event.set()
        # If sync delay is disabled (0), release immediately
        if self.sync_delay_sec <= 0.0:
            self._release_frame(df)

    def wait_for_ai_work(self, timeout: float = 0.05) -> None:
        self._ai_wake_event.wait(timeout)
        self._ai_wake_event.clear()

    def latest_decoded(self, cam_id: str) -> DecodedFrame | None:
        with self._lock:
            return self._latest_decoded.get(cam_id)

    def record_ai_tracks(
        self,
        cam_id: str,
        ts_capture_mono: float,
        tracks: list[TrackedPerson],
        inference_ms: int,
    ) -> None:
        with self._lock:
            hist = self._ai_history.setdefault(cam_id, deque(maxlen=16))
            hist.append(
                AiTrackSnapshot(
                    ts_mono=ts_capture_mono,
                    tracks=list(tracks),
                    inference_ms=inference_ms,
                )
            )

    def register_mjpeg_waiter(self, cam_id: str) -> asyncio.Event:
        ev = asyncio.Event()
        with self._lock:
            self._mjpeg_waiters.setdefault(cam_id, set()).add(ev)
        return ev

    def unregister_mjpeg_waiter(self, cam_id: str, ev: asyncio.Event) -> None:
        with self._lock:
            waiters = self._mjpeg_waiters.get(cam_id)
            if waiters is not None:
                waiters.discard(ev)
                if not waiters:
                    self._mjpeg_waiters.pop(cam_id, None)

    def latest_released(self, cam_id: str) -> DecodedFrame | None:
        with self._lock:
            return self._released.get(cam_id) or self._latest_decoded.get(cam_id)

    def encode_for_viewer(self, df: DecodedFrame, view: str) -> bytes:
        jpg, enc_ms = df.get_encoded_jpeg(
            view=view,
            grid_w=self.grid_w,
            grid_q=self.grid_q,
            focus_w=self.focus_w,
            focus_q=self.focus_q,
        )
        if enc_ms > 0.0:
            with self._lock:
                m = self._metrics.setdefault(df.cam_id, {})
                m["encode_ms"] = round(enc_ms, 2)
        return jpg

    def record_valve_timeout(self, cam_id: str) -> None:
        with self._lock:
            m = self._metrics.setdefault(cam_id, {})
            m["mjpeg_valve_timeouts"] = int(m.get("mjpeg_valve_timeouts", 0)) + 1

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._metrics.items()}

    def _release_frame(self, df: DecodedFrame) -> None:
        cam_id = df.cam_id
        with self._lock:
            if self._last_released_id.get(cam_id, 0) >= df.frame_id:
                return
            self._last_released_id[cam_id] = df.frame_id
            self._released[cam_id] = df
            history = list(self._ai_history.get(cam_id, ()))
            zone = list(self._zones.get(cam_id, ()))
            loop = self._loop
            waiters = list(self._mjpeg_waiters.get(cam_id, ()))

        # Compute interpolated BBoxes at df.ts_mono
        persons, infer_ms, extrapolated = _interpolate_tracks(history, df.ts_mono)
        has_zone = len(zone) >= 3
        in_zone_count = 0
        for p in persons:
            ax = p["foot_x"] if self.anchor_mode == "bottom_center" else p["cx"]
            ay = p["foot_y"] if self.anchor_mode == "bottom_center" else p["cy"]
            in_zone = point_in_polygon(ax, ay, zone) if has_zone else False
            p["in_zone"] = in_zone
            if in_zone:
                in_zone_count += 1

        delay_ms = round((time.monotonic() - df.ts_mono) * 1000.0)
        with self._lock:
            m = self._metrics.setdefault(cam_id, {})
            m["e2e_ms"] = delay_ms
            if extrapolated:
                m["extrapolated_frames"] = int(m.get("extrapolated_frames", 0)) + 1

        if self._on_bbox_ready is not None:
            bbox_msg = {
                "type": "bbox",
                "cam_id": cam_id,
                "frame_id": df.frame_id,
                "ts_capture": df.ts_wall,
                "delay_ms": delay_ms,
                "inference_ms": infer_ms,
                "in_zone_count": in_zone_count,
                "persons": persons,
            }
            try:
                self._on_bbox_ready(bbox_msg)
            except Exception as exc:  # noqa: BLE001
                logger.debug("on_bbox_ready error cam=%s: %s", cam_id, exc)

        if loop is not None and not loop.is_closed() and waiters:
            for ev in waiters:
                try:
                    loop.call_soon_threadsafe(ev.set)
                except RuntimeError:
                    pass

    def _pacer_loop(self) -> None:
        while not self._stop_event.is_set():
            if self.sync_delay_sec <= 0.0:
                self._stop_event.wait(0.1)
                continue

            now = time.monotonic()
            to_release: list[DecodedFrame] = []
            with self._lock:
                for cam_id, ring in self._ring.items():
                    last_rel = self._last_released_id.get(cam_id, 0)
                    # Find oldest unreleased frame whose release time (ts_mono + sync_delay_sec) has arrived
                    candidate: DecodedFrame | None = None
                    for df in ring:
                        if df.frame_id <= last_rel:
                            continue
                        if (now - df.ts_mono) >= self.sync_delay_sec:
                            candidate = df
                        else:
                            break
                    if candidate is not None:
                        to_release.append(candidate)

            for df in to_release:
                self._release_frame(df)

            self._stop_event.wait(0.015)
