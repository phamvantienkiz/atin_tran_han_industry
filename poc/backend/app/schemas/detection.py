from pydantic import BaseModel, Field


class FocusDetectionPayload(BaseModel):
    cam_id: str | None = Field(default=None, max_length=64)
