from fastapi import APIRouter

from app.api.v1.endpoints import cameras, config, detections, health, storages

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(config.router)
api_router.include_router(cameras.router)
api_router.include_router(detections.router)
api_router.include_router(storages.router)
