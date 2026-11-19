from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.dependencies.container import get_container
from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService
from app.services.media_service import MediaService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated async database session per request (Production DB mode)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_camera_service() -> CameraService:
    return get_container().camera_service


def get_detection_service() -> DetectionService:
    return get_container().detection_service


def get_media_service() -> MediaService:
    return get_container().media_service
