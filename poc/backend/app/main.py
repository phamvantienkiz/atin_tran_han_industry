from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.dependencies.container import get_container
from app.exceptions.handlers import register_exception_handlers
from app.middlewares import register_middlewares

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    container = get_container()
    if settings.AI_ENABLED and settings.nvr_configured:
        container.detection_service.start()
    elif settings.AI_ENABLED:
        logger.warning("NVR credentials not configured; background AI NVR worker skipped.")
    try:
        yield
    finally:
        container.detection_service.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    register_middlewares(app)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    if settings.SERVE_FRONTEND and settings.frontend_path.is_dir():
        frontend_dir = settings.frontend_path

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

        @app.get("/styles.css", include_in_schema=False)
        def styles() -> FileResponse:
            return FileResponse(frontend_dir / "styles.css")

        if (frontend_dir / "js").is_dir():
            app.mount("/js", StaticFiles(directory=frontend_dir / "js"), name="js")

    return app


app = create_app()
