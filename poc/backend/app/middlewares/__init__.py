from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middlewares.cors import get_cors_config
from app.middlewares.error_handler import ErrorHandlingMiddleware
from app.middlewares.logging import RequestLoggingMiddleware
from app.middlewares.rate_limit import RateLimitMiddleware
from app.middlewares.request_id import RequestIDMiddleware


def register_middlewares(app: FastAPI) -> None:
    """Wire all cross-cutting middlewares in deterministic order.

    Starlette wraps in reverse registration order, so ErrorHandlingMiddleware
    is added first to remain outermost.
    """
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(CORSMiddleware, **get_cors_config())
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)
