from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Camera(Base):
    """ORM model for Camera & Zone configuration (used in Production DB mode)."""

    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    note: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    subtype: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="mjpeg", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    zone: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
