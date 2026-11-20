import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_response_has_request_id_and_timing_headers(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time" in response.headers


@pytest.mark.asyncio
async def test_request_id_is_propagated(client: AsyncClient) -> None:
    custom_id = "req-trace-123"
    response = await client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert response.headers["X-Request-ID"] == custom_id
