"""Shared API response & error envelope helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def build_error_payload(
    *,
    status_code: int,
    code: str,
    message: str,
    path: str = "",
    request_id: str = "-",
    details: Any = None,
) -> dict[str, Any]:
    """Build a Consistent Response error body while preserving FastAPI's `detail` key."""
    return {
        "success": False,
        "statusCode": status_code,
        "message": message,
        "detail": message,
        "error": {
            "code": code,
            "details": details,
        },
        "meta": {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "path": path,
            "requestId": request_id,
        },
    }
