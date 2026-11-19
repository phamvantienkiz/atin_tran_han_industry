from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


class Settings(BaseSettings):
    """Centralized application settings loaded from `.env`."""

    # --- App ---
    APP_NAME: str = "ATIN Tran Han AI Backend"
    ENVIRONMENT: str = "local"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_DISPLAY_NAME: str = "Nhà máy Thủy sản Trần Hân"
    SERVE_FRONTEND: bool = True

    # --- Paths ---
    FRONTEND_DIR: str = "../frontend"
    CAMERAS_FILE: str = "../data/cameras.json"
    MODEL_PATH: str = "../models/yolo26s.onnx"
    STORAGES_DIR: str = "../storages"

    # --- Security & CORS ---
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    RATE_LIMIT_PER_MINUTE: int = 600

    # --- NVR (PoC Direct Mode) ---
    NVR_HOST: str = ""
    NVR_PORT: int = 80
    NVR_USER: str = ""
    NVR_PASS: str = ""

    # --- AI Detector ---
    AI_ENABLED: bool = True
    AI_CONF_THRESHOLD: float = 0.45
    AI_IMGSZ: int = 640
    AI_INTERVAL_SEC: float = 0.5
    AI_FOCUS_INTERVAL_SEC: float = 0.15
    AI_FOCUS_TTL_SEC: float = 15.0
    AI_CONFIRM_SECONDS: float = 2.0
    AI_EVENT_COOLDOWN_SECONDS: float = 60.0

    # --- Database (Production / Alembic) ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/tranhan_ai"

    # --- ATIN Smart VMS Integration (Production) ---
    ATIN_VMS_ENABLED: bool = False
    MQTT_HOST: str = "aioc-stg.atin.vn"
    MQTT_PORT: int = 443
    MQTT_WS_PATH: str = "/mqtt"
    MQTT_USER: str = ""
    MQTT_PASS: str = ""
    MQTT_CLIENT_ID: str = "ai_edge_tranhan_01"
    MQTT_KEEPALIVE: int = 30
    ORGANIZATION_ID: int = 103
    ZONE_ID: int = 51
    AI_MODULE_CODE: str = "ZONE"
    STORAGE_UPLOAD_URL: str = "https://aioc-stg.atin.vn/storage/upload/file"
    STORAGE_CATEGORY: str = "zone"
    BBOX_PUBLISH_INTERVAL: float = 0.2

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @cached_property
    def frontend_path(self) -> Path:
        return _resolve_path(self.FRONTEND_DIR)

    @cached_property
    def cameras_file_path(self) -> Path:
        return _resolve_path(self.CAMERAS_FILE)

    @cached_property
    def model_file_path(self) -> Path:
        return _resolve_path(self.MODEL_PATH)

    @cached_property
    def storages_path(self) -> Path:
        return _resolve_path(self.STORAGES_DIR)

    @property
    def nvr_configured(self) -> bool:
        return bool(self.NVR_HOST.strip() and self.NVR_USER.strip() and self.NVR_PASS.strip())

    @property
    def nvr_base_url(self) -> str:
        return f"http://{self.NVR_HOST.strip()}:{self.NVR_PORT}"


settings = Settings()
