from pydantic import BaseModel, Field


class RecordStartPayload(BaseModel):
    duration_minutes: int = Field(description="5, 10, hoặc 20 phút")
    subtype: int = Field(default=0, ge=0, le=1)


class ExtractFramesPayload(BaseModel):
    skip_frames: int = Field(description="5 hoặc 10 frame liên tiếp")
