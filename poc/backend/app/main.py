import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
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
    container.ws_hub.bind_loop(asyncio.get_running_loop())

    if settings.nvr_configured:
        container.nvr_stream_manager.reset_for_start()
        container.nvr_stream_manager.sync_cameras(container.camera_repo.list_all())
        if settings.AI_ENABLED:
            container.detection_service.start()
    elif settings.AI_ENABLED:
        logger.warning("NVR credentials not configured; background AI NVR worker skipped.")

    try:
        yield
    finally:
        await container.ws_hub.close_all()
        container.detection_service.stop()
        container.nvr_stream_manager.stop_all()


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
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dir), html=True),
            name="frontend",
        )

    return app


app = create_app()
