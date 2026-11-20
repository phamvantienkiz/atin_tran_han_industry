from app.core.config import settings


def get_cors_config() -> dict:
    """Centralize CORS policy sourced from Settings."""
    return {
        "allow_origins": settings.BACKEND_CORS_ORIGINS,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
