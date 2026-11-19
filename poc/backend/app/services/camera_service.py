"""Camera & zone business logic (transport-agnostic)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.exceptions.custom import NotFoundError, UpstreamError
from app.repositories.camera_repository import CameraRepository
from app.schemas.camera import CameraCreate, CameraUpdate, ZonePoint


class CameraService:
    """Manages cameras, zones, and NVR proxy requests."""

    def __init__(
        self,
        repo: CameraRepository,
        nvr_base_url: str,
        nvr_user: str,
        nvr_pass: str,
        nvr_configured: bool,
    ) -> None:
        self._repo = repo
        self._nvr_base_url = nvr_base_url
        self._nvr_user = nvr_user
        self._nvr_pass = nvr_pass
        self._nvr_configured = nvr_configured

    def list_cameras(
        self,
        enabled: bool | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        cameras = self._repo.list_all()
        if enabled is not None:
            cameras = [c for c in cameras if bool(c.get("enabled", True)) is enabled]
        if search and search.strip():
            needle = search.strip().lower()
            cameras = [
                c
                for c in cameras
                if needle in str(c.get("name", "")).lower()
                or needle in str(c.get("note", "")).lower()
                or needle in str(c.get("id", "")).lower()
            ]
        return cameras

    def get_camera(self, cam_id: str) -> dict[str, Any]:
        cam = self._repo.get_by_id(cam_id)
        if cam is None:
            raise NotFoundError(f"Camera '{cam_id}' không tồn tại")
        return cam

    def create_camera(self, payload: CameraCreate) -> dict[str, Any]:
        cameras = self._repo.list_all()
        cam_id = f"ch{payload.channel}"
        if any(c.get("id") == cam_id for c in cameras):
            cam_id = f"ch{payload.channel}_{int(time.time()) % 10000}"

        cam = {
            "id": cam_id,
            "channel": payload.channel,
            "name": payload.name.strip(),
            "note": payload.note.strip(),
            "subtype": payload.subtype,
            "mode": payload.mode,
            "enabled": payload.enabled,
            "zone": [],
        }
        cameras.append(cam)
        self._repo.save_all(cameras)
        return cam

    def update_camera(self, cam_id: str, payload: CameraUpdate) -> dict[str, Any]:
        cameras = self._repo.list_all()
        for cam in cameras:
            if cam.get("id") == cam_id:
                updates = payload.model_dump(exclude_none=True)
                if "name" in updates:
                    updates["name"] = updates["name"].strip()
                if "note" in updates:
                    updates["note"] = updates["note"].strip()
                cam.update(updates)
                self._repo.save_all(cameras)
                return cam
        raise NotFoundError(f"Camera '{cam_id}' không tồn tại")

    def delete_camera(self, cam_id: str) -> dict[str, str]:
        cameras = self._repo.list_all()
        filtered = [c for c in cameras if c.get("id") != cam_id]
        if len(filtered) == len(cameras):
            raise NotFoundError(f"Camera '{cam_id}' không tồn tại")
        self._repo.save_all(filtered)
        return {"status": "deleted", "id": cam_id}

    def save_zone(self, cam_id: str, points: list[ZonePoint]) -> dict[str, Any]:
        cameras = self._repo.list_all()
        for cam in cameras:
            if cam.get("id") == cam_id:
                cam["zone"] = [p.model_dump() for p in points]
                self._repo.save_all(cameras)
                return cam
        raise NotFoundError(f"Camera '{cam_id}' không tồn tại")

    def _require_nvr(self) -> httpx.DigestAuth:
        if not self._nvr_configured:
            raise UpstreamError(
                "Thiếu cấu hình NVR_HOST, NVR_USER hoặc NVR_PASS trong file .env",
                status_code=503,
            )
        return httpx.DigestAuth(self._nvr_user, self._nvr_pass)

    async def fetch_snapshot(self, cam_id: str) -> tuple[bytes, str, int]:
        cam = self.get_camera(cam_id)
        auth = self._require_nvr()
        url = f"{self._nvr_base_url}/cgi-bin/snapshot.cgi?channel={cam['channel']}"
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(auth=auth, timeout=8.0) as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            raise UpstreamError(f"Lỗi kết nối NVR: {exc}", status_code=502) from exc

        if resp.status_code != 200:
            raise UpstreamError("Không lấy được ảnh snapshot", status_code=resp.status_code)

        latency_ms = round((time.perf_counter() - t0) * 1000)
        media_type = resp.headers.get("content-type", "image/jpeg")
        return resp.content, media_type, latency_ms

    async def probe_camera(self, cam_id: str) -> dict[str, Any]:
        cam = self.get_camera(cam_id)
        auth = self._require_nvr()
        url = f"{self._nvr_base_url}/cgi-bin/snapshot.cgi?channel={cam['channel']}"
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(auth=auth, timeout=6.0) as client:
                resp = await client.get(url)
            latency_ms = round((time.perf_counter() - t0) * 1000)
            return {
                "id": cam_id,
                "online": resp.status_code == 200,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "bytes": len(resp.content),
            }
        except httpx.RequestError as exc:
            return {
                "id": cam_id,
                "online": False,
                "error": str(exc),
                "latency_ms": None,
            }

    def build_mjpeg_request(self, cam_id: str, subtype: int | None) -> tuple[str, httpx.DigestAuth]:
        cam = self.get_camera(cam_id)
        auth = self._require_nvr()
        stream_sub = cam.get("subtype", 1) if subtype is None else subtype
        url = f"{self._nvr_base_url}/cgi-bin/mjpg/video.cgi?channel={cam['channel']}&subtype={stream_sub}"
        return url, auth
