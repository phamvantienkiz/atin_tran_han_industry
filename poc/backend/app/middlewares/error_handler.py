from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger
from app.schemas.common import build_error_payload

logger = get_logger("app.errors")


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Outermost catch-all for unhandled exceptions, returning a safe 500 JSON."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception:
            request_id = getattr(request.state, "request_id", "-")
            logger.exception("Unhandled exception [request_id=%s]", request_id)
            return JSONResponse(
                status_code=500,
                content=build_error_payload(
                    status_code=500,
                    code="INTERNAL_SERVER_ERROR",
                    message="Internal server error",
                    path=request.url.path,
                    request_id=request_id,
                ),
            )
