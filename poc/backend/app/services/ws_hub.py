"""Thread-safe WebSocket broadcast hub for real-time AI detections & HUD state."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger("app.services.ws_hub")


class DetectionWsHub:
    """Manages active WebSocket subscribers and broadcasts AI detection snapshots."""

    def __init__(self, max_hz: float = 15.0) -> None:
        self.max_hz = max_hz
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_push_mono: float = 0.0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.debug("WS detection client connected (total=%d)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.debug("WS detection client disconnected (total=%d)", len(self._clients))

    async def close_all(self) -> None:
        clients = list(self._clients)
        self._clients.clear()
        for ws in clients:
            try:
                await ws.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error closing WS client during shutdown: %s", exc)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def _schedule_broadcast(self, payload: dict[str, Any]) -> None:
        asyncio.create_task(self.broadcast(payload))

    def publish_from_thread(
        self,
        detections_map: dict[str, dict[str, Any]],
        *,
        force: bool = False,
    ) -> None:
        """Publish detection update from background AI thread with Hz rate capping."""
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
            self._loop.call_soon_threadsafe(self._schedule_broadcast, payload)
        except RuntimeError:
            pass
