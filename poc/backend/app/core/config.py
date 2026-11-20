from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


class Settings(BaseSettings):
    """Centralized application settings loaded from `.env`."""

    # --- App & Server ---
    APP_NAME: str = "ATIN Smart Fishing"
    ENVIRONMENT: str = "poc"
    DEBUG: bool = True
    PORT: int = 28080
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_DISPLAY_NAME: str = "ATIN Smart Fishing"
    SERVE_FRONTEND: bool = True

    # --- Paths ---
    FRONTEND_DIR: str = "../frontend/out"
    FRONTEND_LEGACY_DIR: str = "../frontend"
    CAMERAS_FILE: str = "../data/cameras.json"
    MODEL_PATH: str = "../models/yolo26s.onnx"
    STORAGES_DIR: str = "../storages"

    # --- Security & CORS ---
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:28080",
        "http://127.0.0.1:28080",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    RATE_LIMIT_PER_MINUTE: int = 600

    # --- NVR (PoC Direct Mode) ---
    NVR_HOST: str = ""
    NVR_PORT: int = 80
    NVR_USER: str = ""
    NVR_PASS: str = ""
    NVR_STREAM_FPS_LIMIT: float = 0.0

    # --- AI Core ---
    AI_ENABLED: bool = True
    AI_RUNTIME: str = "auto"  # auto | onnx_cuda | cpu
    AI_EP: str = "auto"  # auto | cuda | cpu (never TensorRT)
    AI_VRAM_LIMIT_MB: int = 1536
    AI_CONF_THRESHOLD: float = 0.40
    AI_IMGSZ: int = 640
    AI_DECODE_REDUCE: int = 1  # 1 = full IMREAD_COLOR, 2 = IMREAD_REDUCED_COLOR_2
    AI_SNAP_MIN_IOU: float = 0.25
    AI_TARGET_FPS: float = 0.0  # 0 = run as fast as GPU allows
    AI_ANCHOR_MODE: str = "bottom_center"  # bottom_center | center
    AI_PRESENCE_GRACE_SECONDS: float = 2.0
    AI_PRESENCE_WARNING_SECONDS: float = 10.0
    AI_TIMELINE_WINDOW_SECONDS: int = 1800
    AI_INTERVAL_SEC: float = 0.5
    AI_FOCUS_INTERVAL_SEC: float = 0.15
    AI_FOCUS_TTL_SEC: float = 15.0
    AI_CONFIRM_SECONDS: float = 2.0
    AI_EVENT_COOLDOWN_SECONDS: float = 60.0
    WS_PUSH_MAX_HZ: float = 15.0

    # --- Display & Time-Aligned Synced Playback ---
    DISPLAY_GRID_W: int = 960
    DISPLAY_GRID_Q: int = 80
    DISPLAY_FOCUS_W: int = 1920
    DISPLAY_FOCUS_Q: int = 85
    STREAM_SYNC_DELAY_MS: int = 0
    STREAM_VALVE_MS: int = 150
    BBOX_STALE_SECONDS: float = 1.8
    WS_LEGACY_PAYLOAD: bool = False

    # --- SQLite Persistence (PoC) ---
    DB_BACKEND: str = "sqlite"  # sqlite | json
    DB_PATH: str = "../data/tranhan_poc.db"
    ALERT_EVENT_RETENTION_DAYS: int = 90

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
        primary = _resolve_path(self.FRONTEND_DIR)
        if primary.is_dir() and (primary / "index.html").is_file():
            return primary
        legacy = _resolve_path(self.FRONTEND_LEGACY_DIR)
        if legacy.is_dir() and (legacy / "index.html").is_file():
            return legacy
        legacy_backup = legacy / "legacy_vanilla"
        if legacy_backup.is_dir() and (legacy_backup / "index.html").is_file():
            return legacy_backup
        return primary

    @cached_property
    def cameras_file_path(self) -> Path:
        return _resolve_path(self.CAMERAS_FILE)

    @cached_property
    def model_file_path(self) -> Path:
        configured = _resolve_path(self.MODEL_PATH)
        models_dir = configured.parent
        default_path = models_dir / "yolo26s.onnx"
        best_path = models_dir / "yolo26s_best.onnx"
        fp16_path = models_dir / "yolo26s_fp16.onnx"

        # Prefer the factory-person model yolo26s.onnx even if an older .env points to yolo26s_fp16/best
        if configured.name in ("yolo26s_fp16.onnx", "yolo26s_best.onnx") and default_path.is_file():
            return default_path

        if configured.is_file():
            return configured

        for candidate in (default_path, best_path, fp16_path):
            if candidate.is_file():
                return candidate
        return configured

    @cached_property
    def storages_path(self) -> Path:
        return _resolve_path(self.STORAGES_DIR)

    @cached_property
    def db_file_path(self) -> Path:
        return _resolve_path(self.DB_PATH)

    @property
    def nvr_configured(self) -> bool:
        return bool(self.NVR_HOST.strip() and self.NVR_USER.strip() and self.NVR_PASS.strip())

    @property
    def nvr_base_url(self) -> str:
        return f"http://{self.NVR_HOST.strip()}:{self.NVR_PORT}"


settings = Settings()
