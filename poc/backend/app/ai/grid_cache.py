"""Shared demand-driven Latest-Frame JPEG cache for MJPEG Grid View (off asyncio loop)."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.ai.nvr_stream import NvrFramePacket
from app.core.logging import get_logger

logger = get_logger("app.ai.grid_cache")


@dataclass(frozen=True)
class GridFrame:
    """Latest resized/compressed JPEG frame shared across all Grid View viewers."""

    cam_id: str
    subtype: int
    seq: int
    jpeg_bytes: bytes
    ts_mono: float
    size_bytes: int


class GridFrameCache:
    """Per-camera Latest-Frame cache that resizes & re-encodes only when Grid viewers exist."""

    def __init__(
        self,
        grid_width: int = 960,
        jpeg_quality: int = 72,
        max_workers: int = 2,
    ) -> None:
        self.grid_width = max(320, int(grid_width))
        self.jpeg_quality = max(40, min(95, int(jpeg_quality)))
        self._pool = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="grid-enc")

        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopped = False

        self._grid_waiters: dict[str, set[asyncio.Event]] = {}
        self._focus_viewers: dict[str, int] = {}
        self._pending: dict[str, NvrFramePacket] = {}
        self._in_flight: set[str] = set()
        self._cache: dict[str, GridFrame] = {}

        # Per-camera rolling metrics
        self._raw_kb: dict[str, float] = {}
        self._grid_kb: dict[str, float] = {}
        self._encode_ms: dict[str, float] = {}
        self._dropped: dict[str, int] = {}
        self._emit_times: dict[str, deque[float]] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._pending.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def register_grid_waiter(
        self,
        cam_id: str,
        initial_pkt: NvrFramePacket | None = None,
    ) -> asyncio.Event:
        ev = asyncio.Event()
        should_kick = False
        with self._lock:
            self._grid_waiters.setdefault(cam_id, set()).add(ev)
            cached = self._cache.get(cam_id)
            if initial_pkt is not None and (cached is None or cached.seq != initial_pkt.seq):
                should_kick = True
        if should_kick and initial_pkt is not None:
            self.on_raw_frame(initial_pkt)
        return ev

    def unregister_grid_waiter(self, cam_id: str, ev: asyncio.Event) -> None:
        with self._lock:
            waiters = self._grid_waiters.get(cam_id)
            if waiters is not None:
                waiters.discard(ev)
                if not waiters:
                    self._grid_waiters.pop(cam_id, None)
                    self._pending.pop(cam_id, None)

    def register_focus_viewer(self, cam_id: str) -> None:
        with self._lock:
            self._focus_viewers[cam_id] = self._focus_viewers.get(cam_id, 0) + 1

    def unregister_focus_viewer(self, cam_id: str) -> None:
        with self._lock:
            cnt = self._focus_viewers.get(cam_id, 0) - 1
            if cnt <= 0:
                self._focus_viewers.pop(cam_id, None)
            else:
                self._focus_viewers[cam_id] = cnt

    def latest_grid(self, cam_id: str) -> GridFrame | None:
        with self._lock:
            return self._cache.get(cam_id)

    def on_raw_frame(self, pkt: NvrFramePacket) -> None:
        """Accept a new raw NVR packet; encode only if Grid viewers are attached (Latest-Frame only)."""
        cam_id = pkt.cam_id
        raw_kb = round(len(pkt.jpeg_bytes) / 1024.0, 1)
        should_submit = False

        with self._lock:
            self._raw_kb[cam_id] = raw_kb
            if self._stopped or not self._grid_waiters.get(cam_id):
                return
            if cam_id in self._pending:
                self._dropped[cam_id] = self._dropped.get(cam_id, 0) + 1
            self._pending[cam_id] = pkt
            if cam_id not in self._in_flight:
                self._in_flight.add(cam_id)
                should_submit = True

        if should_submit:
            try:
                self._pool.submit(self._encode_worker, cam_id)
            except RuntimeError:
                with self._lock:
                    self._in_flight.discard(cam_id)

    def _encode_jpeg(self, jpeg_bytes: bytes) -> bytes:
        """Decode (DCT 1/2 when grid_width <= 960), resize if needed, and re-encode JPEG."""
        buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        flag = cv2.IMREAD_REDUCED_COLOR_2 if self.grid_width <= 960 else cv2.IMREAD_COLOR
        img = cv2.imdecode(buf, flag)
        if img is None:
            return jpeg_bytes

        h, w = img.shape[:2]
        if w > self.grid_width:
            new_h = max(2, round(h * (self.grid_width / w)))
            img = cv2.resize(img, (self.grid_width, new_h), interpolation=cv2.INTER_AREA)

        ok, enc = cv2.imencode(
            ".jpg",
            img,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        return enc.tobytes() if ok else jpeg_bytes

    def _encode_worker(self, cam_id: str) -> None:
        while True:
            with self._lock:
                if self._stopped or not self._grid_waiters.get(cam_id):
                    self._pending.pop(cam_id, None)
                    self._in_flight.discard(cam_id)
                    return
                pkt = self._pending.pop(cam_id, None)
                if pkt is None:
                    self._in_flight.discard(cam_id)
                    return

            t0 = time.perf_counter()
            try:
                out_bytes = self._encode_jpeg(pkt.jpeg_bytes)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Grid JPEG encode failed cam=%s: %s", cam_id, exc)
                out_bytes = pkt.jpeg_bytes
            enc_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            now_mono = time.monotonic()

            grid_frame = GridFrame(
                cam_id=cam_id,
                subtype=pkt.subtype,
                seq=pkt.seq,
                jpeg_bytes=out_bytes,
                ts_mono=pkt.ts_mono,
                size_bytes=len(out_bytes),
            )

            with self._lock:
                self._cache[cam_id] = grid_frame
                self._grid_kb[cam_id] = round(grid_frame.size_bytes / 1024.0, 1)
                self._encode_ms[cam_id] = enc_ms
                times = self._emit_times.setdefault(cam_id, deque(maxlen=60))
                times.append(now_mono)
                while times and (now_mono - times[0]) > 5.0:
                    times.popleft()
                loop = self._loop
                waiters = list(self._grid_waiters.get(cam_id, ()))

            if loop is not None and not loop.is_closed() and waiters:
                for ev in waiters:
                    try:
                        loop.call_soon_threadsafe(ev.set)
                    except RuntimeError:
                        pass

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        now_mono = time.monotonic()
        with self._lock:
            cam_ids = sorted(
                set(self._raw_kb.keys())
                | set(self._grid_kb.keys())
                | set(self._grid_waiters.keys())
                | set(self._focus_viewers.keys())
            )
            out: dict[str, dict[str, Any]] = {}
            for cid in cam_ids:
                times = self._emit_times.get(cid)
                fps = 0.0
                if times and len(times) >= 2:
                    span = max(0.001, now_mono - times[0])
                    if now_mono - times[-1] <= 3.0:
                        fps = round(len(times) / span, 1)
                out[cid] = {
                    "raw_jpeg_kb": self._raw_kb.get(cid, 0.0),
                    "grid_jpeg_kb": self._grid_kb.get(cid, 0.0),
                    "grid_encode_ms": self._encode_ms.get(cid, 0.0),
                    "grid_fps": fps,
                    "grid_viewers": len(self._grid_waiters.get(cid, ())),
                    "focus_viewers": self._focus_viewers.get(cid, 0),
                    "grid_dropped": self._dropped.get(cid, 0),
                }
            return out
