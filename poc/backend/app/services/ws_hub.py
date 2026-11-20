"""Thread-safe WebSocket broadcast hub with latest-wins per-client coalescing."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger("app.services.ws_hub")


class _ClientSender:
    """Coalescing latest-wins async sender for a single WebSocket client."""

    def __init__(self, ws: WebSocket, on_dead: Any) -> None:
        self.ws = ws
        self._on_dead = on_dead
        self._pending: dict[tuple[str, str], dict[str, Any]] = {}
        self._wake = asyncio.Event()
        self._closed = False
        self._task = asyncio.create_task(self._run(), name="ws-client-sender")

    def enqueue(self, key: tuple[str, str], message: dict[str, Any]) -> None:
        if self._closed:
            return
        self._pending[key] = message
        self._wake.set()

    async def close(self) -> None:
        self._closed = True
        self._wake.set()
        if not self._task.done():
            self._task.cancel()
        try:
            await self.ws.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error closing WS client: %s", exc)

    async def _run(self) -> None:
        try:
            while not self._closed:
                await self._wake.wait()
                self._wake.clear()
                while self._pending and not self._closed:
                    # Pop all current keys and send latest snapshot for each
                    batch = list(self._pending.items())
                    self._pending.clear()
                    for _key, msg in batch:
                        if self._closed:
                            return
                        await self.ws.send_json(msg)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            self._closed = True
            self._on_dead(self.ws)


class DetectionWsHub:
    """Manages active WebSocket subscribers and broadcasts bbox, hud, and legacy snapshots."""

    def __init__(self, max_hz: float = 15.0) -> None:
        self.max_hz = max_hz
        self._clients: dict[WebSocket, _ClientSender] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_push_mono: float = 0.0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients[ws] = _ClientSender(ws, self.disconnect)
        logger.debug("WS detection client connected (total=%d)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        sender = self._clients.pop(ws, None)
        if sender is not None:
            sender._closed = True
            sender._wake.set()
        logger.debug("WS detection client disconnected (total=%d)", len(self._clients))

    async def close_all(self) -> None:
        senders = list(self._clients.values())
        self._clients.clear()
        for sender in senders:
            await sender.close()

    def _enqueue_on_loop(self, key: tuple[str, str], message: dict[str, Any]) -> None:
        for sender in list(self._clients.values()):
            sender.enqueue(key, message)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        msg_type = str(message.get("type", "detections"))
        cam_id = str(message.get("cam_id", "*"))
        self._enqueue_on_loop((msg_type, cam_id), message)

    def publish_bbox_from_thread(self, bbox_msg: dict[str, Any]) -> None:
        """Publish minimal per-camera bbox message immediately (latest-wins)."""
        if not self._clients or self._loop is None or self._loop.is_closed():
            return
        cam_id = str(bbox_msg.get("cam_id", "*"))
        try:
            self._loop.call_soon_threadsafe(self._enqueue_on_loop, ("bbox", cam_id), bbox_msg)
        except RuntimeError:
            pass

    def publish_hud_from_thread(self, hud_msg: dict[str, Any]) -> None:
        """Publish low-frequency HUD/timeline update for a camera (latest-wins)."""
        if not self._clients or self._loop is None or self._loop.is_closed():
            return
        cam_id = str(hud_msg.get("cam_id", "*"))
        try:
            self._loop.call_soon_threadsafe(self._enqueue_on_loop, ("hud", cam_id), hud_msg)
        except RuntimeError:
            pass

    def publish_from_thread(
        self,
        detections_map: dict[str, dict[str, Any]],
        *,
        force: bool = False,
    ) -> None:
        """Legacy combined detection broadcast with Hz rate capping."""
        if not self._clients or self._loop is None or self._loop.is_closed():
            return
        now = time.monotonic()
        min_interval = 1.0 / self.max_hz if self.max_hz > 0 else 0.066
        if not force and (now - self._last_push_mono) < min_interval:
            return
        self._last_push_mono = now
        payload = {
            "type": "detections",
            "ts": time.time(),
            "data": detections_map,
        }
        try:
            self._loop.call_soon_threadsafe(self._enqueue_on_loop, ("detections", "*"), payload)
        except RuntimeError:
            pass
