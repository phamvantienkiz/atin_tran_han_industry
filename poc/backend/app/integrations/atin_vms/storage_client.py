"""ATIN Smart VMS Storage API client (C05: in-RAM JPEG upload -> object_key)."""

from __future__ import annotations

import cv2
import httpx
import numpy as np

from app.core.logging import get_logger

logger = get_logger("app.integrations.atin_vms.storage")


class AtinStorageClient:
    """Uploads event snapshots directly from RAM to ATIN Storage API."""

    def __init__(self, upload_url: str, category: str = "zone", timeout: float = 10.0) -> None:
        self.upload_url = upload_url
        self.category = category
        self.timeout = timeout

    def upload_frame(self, frame: np.ndarray, camera_id: str, quality: int = 85) -> str | None:
        """Encode BGR frame as JPEG in memory and return `object_key` on success."""
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            logger.warning("Failed to encode snapshot JPEG for camera_id=%s", camera_id)
            return None

        files = {"file": ("snapshot.jpg", encoded.tobytes(), "image/jpeg")}
        data = {"camera_id": camera_id, "category": self.category}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.upload_url, files=files, data=data)
            resp.raise_for_status()
            payload = resp.json()
            object_key = payload.get("object_key")
            if not object_key:
                logger.warning("Storage API returned no object_key for camera_id=%s", camera_id)
            return object_key
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("Storage upload failed for camera_id=%s: %s", camera_id, exc)
            return None
