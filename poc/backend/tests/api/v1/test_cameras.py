from pathlib import Path

import pytest
from httpx import AsyncClient

from app.api.deps import get_camera_service
from app.main import create_app
from app.repositories.camera_repository import JsonCameraRepository
from app.services.camera_service import CameraService


@pytest.mark.asyncio
async def test_camera_crud_and_zone_flow(tmp_path: Path) -> None:
    repo = JsonCameraRepository(tmp_path / "cameras.json")
    service = CameraService(
        repo=repo,
        nvr_base_url="http://127.0.0.1:80",
        nvr_user="",
        nvr_pass="",
        nvr_configured=False,
    )

    test_app = create_app()
    test_app.dependency_overrides[get_camera_service] = lambda: service

    from httpx import ASGITransport

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        res_list = await ac.get("/api/v1/cameras")
        assert res_list.status_code == 200
        assert len(res_list.json()) == 4

        res_create = await ac.post(
            "/api/v1/cameras",
            json={"channel": 25, "name": "Cổng kho lạnh", "note": "Test"},
        )
        assert res_create.status_code == 201
        cam_id = res_create.json()["id"]

        res_zone = await ac.put(
            f"/api/v1/cameras/{cam_id}/zone",
            json={"points": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}]},
        )
        assert res_zone.status_code == 200
        assert len(res_zone.json()["zone"]) == 3

        res_filter = await ac.get("/api/v1/cameras?enabled=true&search=kho")
        assert res_filter.status_code == 200
        assert len(res_filter.json()) == 1
        assert res_filter.json()[0]["id"] == cam_id

        res_del = await ac.delete(f"/api/v1/cameras/{cam_id}")
        assert res_del.status_code == 200

        res_missing = await ac.delete(f"/api/v1/cameras/{cam_id}")
        assert res_missing.status_code == 404
        err_body = res_missing.json()
        assert err_body["success"] is False
        assert err_body["statusCode"] == 404
        assert err_body["error"]["code"] == "NOT_FOUND"
        assert "requestId" in err_body["meta"]
