from pydantic import BaseModel, Field


class ZonePoint(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ZonePayload(BaseModel):
    points: list[ZonePoint]


class CameraCreate(BaseModel):
    channel: int = Field(ge=1, le=128)
    name: str = Field(min_length=1, max_length=120)
    zone_name: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=240)
    subtype: int = Field(default=1, ge=0, le=2)
    mode: str = Field(default="mjpeg", pattern="^(mjpeg|snapshot)$")
    feature_type: str = Field(default="zone_presence", pattern="^(zone_presence|zone_intrusion)$")
    grace_seconds: float = Field(default=2.0, ge=0.0, le=60.0)
    warning_seconds: float = Field(default=10.0, ge=1.0, le=600.0)
    enabled: bool = True


class CameraUpdate(BaseModel):
    channel: int | None = Field(default=None, ge=1, le=128)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    zone_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=240)
    subtype: int | None = Field(default=None, ge=0, le=2)
    mode: str | None = Field(default=None, pattern="^(mjpeg|snapshot)$")
    feature_type: str | None = Field(default=None, pattern="^(zone_presence|zone_intrusion)$")
    grace_seconds: float | None = Field(default=None, ge=0.0, le=60.0)
    warning_seconds: float | None = Field(default=None, ge=1.0, le=600.0)
    enabled: bool | None = None


class CameraRead(BaseModel):
    id: str
    channel: int
    name: str
    zone_name: str = ""
    note: str = ""
    subtype: int = 1
    mode: str = "mjpeg"
    feature_type: str = "zone_presence"
    grace_seconds: float = 2.0
    warning_seconds: float = 10.0
    enabled: bool = True
    zone: list[ZonePoint] = Field(default_factory=list)
