"""Shared in-RAM NVR MJPEG/Snapshot stream reader (1 upstream connection per camera)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import httpx
import numpy as np

from app.core.logging import get_logger

logger = get_logger("app.ai.nvr_stream")

_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"
_MAX_BUFFER_BYTES = 4 * 1024 * 1024
_MJPEG_STALL_TIMEOUT_SEC = 4.0
_SNAPSHOT_FALLBACK_WINDOW_SEC = 15.0
_SNAPSHOT_POLL_INTERVAL_SEC = 0.30


@dataclass(frozen=True)
class NvrFramePacket:
    """Latest frame captured from an NVR channel, shared by AI Core and MJPEG HTTP endpoints."""

    cam_id: str
    channel: int
    subtype: int
    frame: np.ndarray
    jpeg_bytes: bytes
    seq: int
    ts_mono: float
    ts_wall: float


def extract_jpeg_frames(buffer: bytearray) -> list[bytes]:
    """Extract all complete JPEG frames (SOI..EOI) from a byte buffer in place."""
    frames: list[bytes] = []
    while True:
        start = buffer.find(_JPEG_SOI)
        if start == -1:
            if len(buffer) > 2:
                del buffer[:-2]
            break
        if start > 0:
            del buffer[:start]

        end = buffer.find(_JPEG_EOI, 2)
        if end == -1:
            if len(buffer) > _MAX_BUFFER_BYTES:
                del buffer[:]
            break

        frame_end = end + 2
        frames.append(bytes(buffer[:frame_end]))
        del buffer[:frame_end]
    return frames


class NvrChannelReader:
    """Daemon thread ingesting a single NVR channel via MJPEG with Snapshot fallback."""

    def __init__(
        self,
        cam_id: str,
        channel: int,
        subtype: int,
        nvr_base_url: str,
        nvr_user: str,
        nvr_pass: str,
        fps_limit: float = 12.0,
    ) -> None:
        self.cam_id = cam_id
        self.channel = channel
        self.subtype = subtype
        self._nvr_base_url = nvr_base_url.rstrip("/")
        self._nvr_user = nvr_user
        self._nvr_pass = nvr_pass
        self._min_decode_interval = 1.0 / fps_limit if fps_limit > 0 else 0.0

        self._lock = threading.Lock()
        self._latest: NvrFramePacket | None = None
        self._seq: int = 0
        self._last_decode_mono: float = 0.0

        self._stop_event = threading.Event()
        self._client_lock = threading.Lock()
        self._active_client: httpx.Client | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"nvr-stream-{self.cam_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._client_lock:
            client = self._active_client
        if client is not None:
            try:
                client.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Ignoring client close error cam=%s: %s", self.cam_id, exc)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def latest(self) -> NvrFramePacket | None:
        with self._lock:
            return self._latest

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _store_jpeg(self, jpeg_bytes: bytes, force_decode: bool = False) -> bool:
        now_mono = time.monotonic()
        with self._lock:
            existing = self._latest

        should_decode = (
            force_decode
            or existing is None
            or self._min_decode_interval <= 0.0
            or (now_mono - self._last_decode_mono) >= self._min_decode_interval
        )

        if should_decode:
            buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is None:
                return False
            self._last_decode_mono = now_mono
            with self._lock:
                self._seq += 1
                self._latest = NvrFramePacket(
                    cam_id=self.cam_id,
                    channel=self.channel,
                    subtype=self.subtype,
                    frame=frame,
                    jpeg_bytes=jpeg_bytes,
                    seq=self._seq,
                    ts_mono=now_mono,
                    ts_wall=time.time(),
                )
            return True

        # Keep JPEG fresh for MJPEG web clients even between AI decode intervals
        with self._lock:
            if self._latest is not None:
                self._seq += 1
                self._latest = NvrFramePacket(
                    cam_id=self.cam_id,
                    channel=self.channel,
                    subtype=self.subtype,
                    frame=self._latest.frame,
                    jpeg_bytes=jpeg_bytes,
                    seq=self._seq,
                    ts_mono=now_mono,
                    ts_wall=time.time(),
                )
        return True

    def _set_active_client(self, client: httpx.Client | None) -> None:
        with self._client_lock:
            self._active_client = client

    def _stream_mjpeg_once(self) -> None:
        url = f"{self._nvr_base_url}/cgi-bin/mjpg/video.cgi?channel={self.channel}&subtype={self.subtype}"
        auth = httpx.DigestAuth(self._nvr_user, self._nvr_pass)
        timeout = httpx.Timeout(10.0, read=15.0)
        buffer = bytearray()

        with httpx.Client(auth=auth, timeout=timeout) as client:
            self._set_active_client(client)
            try:
                with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"MJPEG HTTP {resp.status_code}")
                    last_frame_mono = time.monotonic()
                    for chunk in resp.iter_bytes(chunk_size=16384):
                        if self._stop_event.is_set():
                            return
                        if not chunk:
                            continue
                        buffer.extend(chunk)
                        jpegs = extract_jpeg_frames(buffer)
                        if jpegs:
                            # Keep only the newest JPEG if multiple arrived in one chunk
                            if self._store_jpeg(jpegs[-1]):
                                last_frame_mono = time.monotonic()
                        elif (time.monotonic() - last_frame_mono) > _MJPEG_STALL_TIMEOUT_SEC:
                            raise TimeoutError("MJPEG stream stalled without JPEG frames")
            finally:
                self._set_active_client(None)

    def _poll_snapshots_fallback(self, duration_sec: float = _SNAPSHOT_FALLBACK_WINDOW_SEC) -> None:
        url = f"{self._nvr_base_url}/cgi-bin/snapshot.cgi?channel={self.channel}"
        auth = httpx.DigestAuth(self._nvr_user, self._nvr_pass)
        deadline = time.monotonic() + duration_sec

        with httpx.Client(auth=auth, timeout=6.0) as client:
            self._set_active_client(client)
            try:
                while not self._stop_event.is_set() and time.monotonic() < deadline:
                    t0 = time.monotonic()
                    try:
                        resp = client.get(url)
                        if resp.status_code == 200 and resp.content:
                            self._store_jpeg(resp.content, force_decode=True)
                    except httpx.HTTPError as exc:
                        logger.debug("Snapshot fallback failed cam=%s: %s", self.cam_id, exc)
                    elapsed = time.monotonic() - t0
                    remaining = max(0.0, _SNAPSHOT_POLL_INTERVAL_SEC - elapsed)
                    if remaining > 0:
                        self._stop_event.wait(remaining)
            finally:
                self._set_active_client(None)

    def _run(self) -> None:
        logger.info(
            "Starting NVR stream reader cam=%s ch=%s subtype=%s",
            self.cam_id,
            self.channel,
            self.subtype,
        )
        while not self._stop_event.is_set():
            try:
                self._stream_mjpeg_once()
            except Exception as exc:  # noqa: BLE001 - resilient stream recovery
                if self._stop_event.is_set():
                    break
                logger.warning(
                    "MJPEG reader cam=%s (ch=%s) interrupted (%s); switching to snapshot fallback for %.0fs",
                    self.cam_id,
                    self.channel,
                    exc,
                    _SNAPSHOT_FALLBACK_WINDOW_SEC,
                )
                self._poll_snapshots_fallback(_SNAPSHOT_FALLBACK_WINDOW_SEC)
                if not self._stop_event.is_set():
                    self._stop_event.wait(0.5)
        logger.info("Stopped NVR stream reader cam=%s", self.cam_id)


class NvrStreamManager:
    """Manages one shared NvrChannelReader per enabled camera."""

    def __init__(
        self,
        nvr_base_url: str,
        nvr_user: str,
        nvr_pass: str,
        nvr_configured: bool,
        fps_limit: float = 12.0,
    ) -> None:
        self._nvr_base_url = nvr_base_url
        self._nvr_user = nvr_user
        self._nvr_pass = nvr_pass
        self._nvr_configured = nvr_configured
        self._fps_limit = fps_limit
        self._lock = threading.Lock()
        self._readers: dict[str, NvrChannelReader] = {}
        self._stopped = False

    def sync_cameras(self, cameras: list[dict[str, Any]]) -> None:
        """Start, restart (if channel/subtype changed), or stop readers to match camera list."""
        if not self._nvr_configured:
            return
        with self._lock:
            if self._stopped:
                return
            desired: dict[str, tuple[int, int]] = {}
            for cam in cameras:
                if not cam.get("enabled", True):
                    continue
                cam_id = str(cam["id"])
                channel = int(cam["channel"])
                subtype = int(cam.get("subtype", 1))
                desired[cam_id] = (channel, subtype)

            to_stop: list[NvrChannelReader] = []
            for cam_id in list(self._readers.keys()):
                reader = self._readers[cam_id]
                spec = desired.get(cam_id)
                if spec is None or (reader.channel, reader.subtype) != spec:
                    to_stop.append(self._readers.pop(cam_id))

            for cam_id, (channel, subtype) in desired.items():
                existing = self._readers.get(cam_id)
                if existing is None or not existing.is_alive:
                    reader = NvrChannelReader(
                        cam_id=cam_id,
                        channel=channel,
                        subtype=subtype,
                        nvr_base_url=self._nvr_base_url,
                        nvr_user=self._nvr_user,
                        nvr_pass=self._nvr_pass,
                        fps_limit=self._fps_limit,
                    )
                    reader.start()
                    self._readers[cam_id] = reader

        for reader in to_stop:
            reader.stop()

    def latest(self, cam_id: str) -> NvrFramePacket | None:
        with self._lock:
            reader = self._readers.get(cam_id)
        return reader.latest() if reader is not None else None

    def active_camera_ids(self) -> list[str]:
        with self._lock:
            return list(self._readers.keys())

    def reset_for_start(self) -> None:
        with self._lock:
            self._stopped = False

    def stop_all(self) -> None:
        with self._lock:
            self._stopped = True
            readers = list(self._readers.values())
            self._readers.clear()
        for reader in readers:
            reader.stop()
