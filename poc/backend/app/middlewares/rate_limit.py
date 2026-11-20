import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.schemas.common import build_error_payload

WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window in-memory rate limiter keyed by client IP.

    TODO: Swap `_hits` for a Redis-backed counter in multi-instance production.
    """

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        window = self._hits[client_ip]
        window[:] = [t for t in window if now - t < WINDOW_SECONDS]

        if len(window) >= settings.RATE_LIMIT_PER_MINUTE:
            request_id = getattr(request.state, "request_id", "-")
            return JSONResponse(
                status_code=429,
                content=build_error_payload(
                    status_code=429,
                    code="RATE_LIMIT_EXCEEDED",
                    message="Too many requests, please try again later.",
                    path=request.url.path,
                    request_id=request_id,
                ),
            )

        window.append(now)
        return await call_next(request)
