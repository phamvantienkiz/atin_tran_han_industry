import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.ai.nvr_stream import NvrFramePacket, NvrStreamManager
from app.ai.worker import PersonZoneDetector
from app.api.deps import (
    get_camera_service,
    get_detection_service,
    get_nvr_stream_manager,
    get_ws_hub,
)
from app.main import create_app
from app.repositories.camera_repository import JsonCameraRepository
from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService
from app.services.ws_hub import DetectionWsHub


class _StubStreamManager(NvrStreamManager):
    def __init__(self, packets: dict[str, NvrFramePacket]) -> None:
        super().__init__("http://127.0.0.1:80", "", "", nvr_configured=False)
        self._packets = packets

    def latest(self, cam_id: str) -> NvrFramePacket | None:
        return self._packets.get(cam_id)


@pytest.mark.asyncio
async def test_config_and_camera_extended_fields_and_reset_stats(tmp_path: Path) -> None:
    repo = JsonCameraRepository(tmp_path / "cameras.json")
    stub_pkt = NvrFramePacket(
        cam_id="ch16",
        channel=16,
        subtype=0,
        frame=np.zeros((16, 16, 3), dtype=np.uint8),
        jpeg_bytes=b"\xff\xd8\xff\xe0MOCKJPEG\xff\xd9",
        seq=1,
        ts_mono=time.monotonic(),
        ts_wall=time.time(),
    )
    stream_mgr = _StubStreamManager({"ch16": stub_pkt})
    cam_service = CameraService(
        repo=repo,
        nvr_base_url="http://127.0.0.1:80",
        nvr_user="",
        nvr_pass="",
        nvr_configured=False,
        nvr_stream_manager=stream_mgr,
    )
    detector = PersonZoneDetector(
        model_path=tmp_path / "missing.onnx",
        nvr_base_url="http://127.0.0.1:80",
        nvr_user="",
        nvr_pass="",
        load_cameras_fn=repo.list_all,
    )
    det_service = DetectionService(detector=detector, camera_service=cam_service)

    test_app = create_app()
    test_app.dependency_overrides[get_camera_service] = lambda: cam_service
    test_app.dependency_overrides[get_detection_service] = lambda: det_service
    test_app.dependency_overrides[get_nvr_stream_manager] = lambda: stream_mgr

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        # 1. Config exposes PoC v001 metadata
        cfg_res = await ac.get("/api/v1/config")
        assert cfg_res.status_code == 200
        cfg = cfg_res.json()
        assert cfg["ws_path"] == "/api/v1/ws/detections"
        assert cfg["timeline_window_sec"] == 1800
        assert "ai_runtime" in cfg

        # 2. Camera create/update persists zone_name, feature_type, grace_seconds, warning_seconds
        create_res = await ac.post(
            "/api/v1/cameras",
            json={
                "channel": 30,
                "name": "Máy trộn 1",
                "zone_name": "Vùng máy trộn",
                "note": "Giám sát nhân viên",
                "feature_type": "zone_presence",
                "grace_seconds": 3.0,
                "warning_seconds": 15.0,
            },
        )
        assert create_res.status_code == 201
        created = create_res.json()
        assert created["zone_name"] == "Vùng máy trộn"
        assert created["grace_seconds"] == 3.0
        assert created["warning_seconds"] == 15.0

        # 3. Reset stats returns 200 for valid camera and 404 for unknown
        reset_ok = await ac.post(f"/api/v1/detections/{created['id']}/reset-stats")
        assert reset_ok.status_code == 200
        assert reset_ok.json() == {"status": "reset", "cam_id": created["id"]}

        reset_404 = await ac.post("/api/v1/detections/unknown_cam/reset-stats")
        assert reset_404.status_code == 404

        # 4. Snapshot fast-path reads from RAM NvrStreamManager with 0ms latency
        snap_res = await ac.get("/api/v1/cameras/ch16/snapshot.jpg")
        assert snap_res.status_code == 200
        assert snap_res.content == stub_pkt.jpeg_bytes
        assert snap_res.headers["X-Latency-Ms"] == "0"


def test_detections_websocket_both_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "NVR_HOST", "")
    repo = JsonCameraRepository(tmp_path / "cameras.json")
    cam_service = CameraService(
        repo=repo,
        nvr_base_url="http://127.0.0.1:80",
        nvr_user="",
        nvr_pass="",
        nvr_configured=False,
    )
    detector = PersonZoneDetector(
        model_path=tmp_path / "missing.onnx",
        nvr_base_url="http://127.0.0.1:80",
        nvr_user="",
        nvr_pass="",
        load_cameras_fn=repo.list_all,
    )
    det_service = DetectionService(detector=detector, camera_service=cam_service)
    ws_hub = DetectionWsHub(max_hz=15.0)

    test_app = create_app()
    test_app.dependency_overrides[get_camera_service] = lambda: cam_service
    test_app.dependency_overrides[get_detection_service] = lambda: det_service
    test_app.dependency_overrides[get_ws_hub] = lambda: ws_hub

    with TestClient(test_app) as sync_client:
        for ws_url in ("/api/v1/ws/detections", "/api/v1/detections/ws"):
            with sync_client.websocket_connect(ws_url) as ws:
                initial = ws.receive_json()
                assert initial["type"] == "detections"
                assert isinstance(initial["data"], dict)
                ws.send_json({"type": "focus", "cam_id": "ch16"})
        assert ws_hub.client_count == 0
