"""Interaction schemas — danmaku, like, gift, forbidden-word request/response models."""

from pydantic import BaseModel, Field, field_validator

from app.models.interaction import MAX_PIN_DURATION_SECONDS


# ── Danmaku ───────────────────────────────────────────────────────


class DanmakuSendRequest(BaseModel):
    """Send a danmaku (bullet comment) in a room."""

    content: str = Field(..., min_length=1, max_length=100, description="弹幕内容")
    color: str = Field(default="#FFFFFF", max_length=7, description="颜色 (HEX)")
    is_pinned: bool = Field(default=False, description="是否置顶")
    pin_duration_seconds: int | None = Field(
        default=None, ge=1, le=MAX_PIN_DURATION_SECONDS, description="置顶时长(秒)"
    )

    @field_validator("color")
    @classmethod
    def validate_color_hex(cls, v: str) -> str:
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("颜色必须为 HEX 格式，如 #FFFFFF")
        return v.upper()


class DanmakuResponse(BaseModel):
    """Danmaku returned to clients."""

    id: int
    room_id: int
    user_id: int
    username: str = ""
    nickname: str = ""
    content: str
    color: str
    is_pinned: bool = False
    pin_duration_seconds: int | None = None
    created_at: str  # ISO 8601

    model_config = {"from_attributes": True}


# ── Like ──────────────────────────────────────────────────────────


class LikeResponse(BaseModel):
    """Like response."""

    room_id: int
    user_id: int
    total_likes: int  # Total likes this user has given in this room


# ── Gift ──────────────────────────────────────────────────────────


class GiftResponse(BaseModel):
    """Gift catalog item."""

    id: int
    name: str
    price_fen: int
    effect: str
    icon_url: str | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class SendGiftRequest(BaseModel):
    """Send a gift in a room."""

    gift_id: int = Field(..., ge=1, description="礼物 ID")
    quantity: int = Field(default=1, ge=1, le=99, description="数量")


class SendGiftResponse(BaseModel):
    """Response after sending a gift."""

    gift_record_id: int
    gift_name: str
    quantity: int
    total_amount_fen: int
    balance_after_fen: int  # Sender's remaining balance
    is_announcement: bool = False  # Whether to trigger room-wide announcement


class GiftRankItem(BaseModel):
    """Gift leaderboard item for a room."""

    user_id: int
    username: str
    nickname: str
    avatar_url: str | None = None
    total_amount_fen: int
    rank: int


# ── Forbidden Word (admin) ────────────────────────────────────────


class ForbiddenWordCreateRequest(BaseModel):
    """Admin: add a forbidden word."""

    word: str = Field(..., min_length=1, max_length=50, description="违禁词")


class ForbiddenWordResponse(BaseModel):
    """Forbidden word returned to clients."""

    id: int
    word: str
    created_at: str  # ISO 8601

    model_config = {"from_attributes": True}
