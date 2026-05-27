"""Room schemas — request/response models for livestream room management."""

from pydantic import BaseModel, Field, field_validator

from app.models.room import ROOM_CATEGORIES

VALID_CATEGORIES = set(ROOM_CATEGORIES.keys())


# ── Request schemas ────────────────────────────────────────────────


class CreateRoomRequest(BaseModel):
    """Create a new room. Requires streamer role + verified identity."""

    title: str = Field(..., min_length=2, max_length=50, description="直播间标题")
    description: str | None = Field(default=None, max_length=500, description="直播间简介")
    category: str = Field(default="other", description="分类")
    cover_url: str | None = Field(default=None, max_length=500, description="封面图URL")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"无效的分类，可选值: {', '.join(sorted(VALID_CATEGORIES))}")
        return v


class UpdateRoomRequest(BaseModel):
    """Update room info. All fields optional — only provided fields are updated."""

    title: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None)
    cover_url: str | None = Field(default=None, max_length=500)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(f"无效的分类，可选值: {', '.join(sorted(VALID_CATEGORIES))}")
        return v


class BanRoomRequest(BaseModel):
    """Admin: ban a room."""

    reason: str = Field(..., min_length=1, max_length=500, description="封禁原因")


# ── Response schemas ───────────────────────────────────────────────


class StreamerBrief(BaseModel):
    """Minimal streamer info embedded in room responses."""

    id: int
    username: str
    nickname: str
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    """Full room detail returned to clients."""

    id: int
    streamer_id: int
    title: str
    description: str | None = None
    category: str
    cover_url: str | None = None
    status: str
    peak_viewers: int = 0
    current_viewers: int = 0
    total_sessions: int = 0
    started_at: str | None = None  # ISO 8601
    ended_at: str | None = None  # ISO 8601
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    streamer: StreamerBrief | None = None

    model_config = {"from_attributes": True}


class RoomListItem(BaseModel):
    """Room item in list responses (lighter than RoomResponse)."""

    id: int
    streamer_id: int
    title: str
    category: str
    cover_url: str | None = None
    status: str
    current_viewers: int = 0
    started_at: str | None = None  # ISO 8601
    streamer: StreamerBrief | None = None

    model_config = {"from_attributes": True}


class RoomStats(BaseModel):
    """Room session stats returned after ending a stream."""

    room_id: int
    session_duration_seconds: int
    peak_viewers: int
    total_sessions: int
