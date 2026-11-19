import logging
import logging.config
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def setup_logging() -> None:
    """Configure root console and rotating file logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {"format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s"},
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"},
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(LOG_DIR / "app.log"),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 3,
                    "encoding": "utf-8",
                    "formatter": "default",
                },
            },
            "root": {"level": "INFO", "handlers": ["console", "file"]},
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger wired to the centralized configuration."""
    return logging.getLogger(name)
