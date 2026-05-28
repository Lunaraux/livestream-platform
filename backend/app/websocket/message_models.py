"""WebSocket message schemas — Pydantic models for client↔server messages.

Per 07-realtime.md message protocol:
  All messages are JSON: {"type": "...", "data": {...}}
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════════════
# Client → Server message types
# ═══════════════════════════════════════════════════════════════════

class PingMessage(BaseModel):
    """Client heartbeat ping."""
    type: str = "ping"


class DanmakuMessageData(BaseModel):
    """Danmaku send payload from client."""
    content: str = Field(..., min_length=1, max_length=200, description="弹幕内容")
    color: str = Field(default="#ffffff", description="弹幕颜色")


class DanmakuMessage(BaseModel):
    """Client sends danmaku."""
    type: str = "danmaku"
    data: DanmakuMessageData


class LikeMessage(BaseModel):
    """Client sends like."""
    type: str = "like"
    data: dict = Field(default_factory=dict)


# Union of all possible client messages
CLIENT_MESSAGE_TYPES = {
    "ping": PingMessage,
    "danmaku": DanmakuMessage,
    "like": LikeMessage,
}


# ═══════════════════════════════════════════════════════════════════
# Server → Client message types
# ═══════════════════════════════════════════════════════════════════

class PongData(BaseModel):
    """Heartbeat response."""
    server_time: int


class DanmakuBroadcastData(BaseModel):
    """Danmaku broadcast to all viewers in a room."""
    user_id: int
    nickname: str
    level: int
    content: str
    color: str


class LikeBroadcastData(BaseModel):
    """Like count broadcast."""
    count: int


class GiftBroadcastData(BaseModel):
    """Gift broadcast to all viewers."""
    user_id: int
    nickname: str
    gift_name: str
    quantity: int
    total_fen: int


class GiftSpecialData(BaseModel):
    """Large gift full-screen announcement."""
    user_id: int
    nickname: str
    gift_name: str
    quantity: int
    total_fen: int
    effect_type: str


class ViewerUpdateData(BaseModel):
    """Online viewer count update."""
    count: int


class RoomBannedData(BaseModel):
    """Room banned notification."""
    reason: str


class AnnouncementData(BaseModel):
    """System announcement."""
    content: str


class UserEnterData(BaseModel):
    """High-level user enter notification (level >= 5)."""
    nickname: str
    level: int


class ErrorData(BaseModel):
    """Error message to a specific client."""
    message: str
    code: int = 1001


# ═══════════════════════════════════════════════════════════════════
# Message routing helper
# ═══════════════════════════════════════════════════════════════════

SERVER_MESSAGE_FACTORIES = {
    "pong": lambda **d: {"type": "pong", "data": PongData(**d).model_dump()},
    "danmaku": lambda **d: {"type": "danmaku", "data": DanmakuBroadcastData(**d).model_dump()},
    "like": lambda **d: {"type": "like", "data": LikeBroadcastData(**d).model_dump()},
    "gift": lambda **d: {"type": "gift", "data": GiftBroadcastData(**d).model_dump()},
    "gift_special": lambda **d: {"type": "gift_special", "data": GiftSpecialData(**d).model_dump()},
    "viewer_update": lambda **d: {"type": "viewer_update", "data": ViewerUpdateData(**d).model_dump()},
    "room_banned": lambda **d: {"type": "room_banned", "data": RoomBannedData(**d).model_dump()},
    "announcement": lambda **d: {"type": "announcement", "data": AnnouncementData(**d).model_dump()},
    "user_enter": lambda **d: {"type": "user_enter", "data": UserEnterData(**d).model_dump()},
    "error": lambda **d: {"type": "error", "data": ErrorData(**d).model_dump()},
}


def make_server_message(msg_type: str, **data) -> dict:
    """Build a server→client message dict from type and data kwargs."""
    factory = SERVER_MESSAGE_FACTORIES.get(msg_type)
    if factory is None:
        return {"type": msg_type, "data": data}
    return factory(**data)
