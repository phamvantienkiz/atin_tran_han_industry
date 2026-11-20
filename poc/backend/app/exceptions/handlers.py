from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions.custom import ConflictError, NotFoundError, UpstreamError, ValidationError
from app.schemas.common import build_error_payload


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "-")
    return JSONResponse(
        status_code=status_code,
        content=build_error_payload(
            status_code=status_code,
            code=code,
            message=message,
            path=request.url.path,
            request_id=request_id,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register typed domain exception handlers."""

    @app.exception_handler(NotFoundError)
    def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(request, 404, "NOT_FOUND", str(exc))

    @app.exception_handler(ConflictError)
    def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return _error_response(request, 409, "CONFLICT", str(exc))

    @app.exception_handler(ValidationError)
    def handle_validation(request: Request, exc: ValidationError) -> JSONResponse:
        return _error_response(request, 422, "VALIDATION_ERROR", str(exc))

    @app.exception_handler(UpstreamError)
    def handle_upstream(request: Request, exc: UpstreamError) -> JSONResponse:
        return _error_response(request, exc.status_code, "UPSTREAM_ERROR", str(exc))
