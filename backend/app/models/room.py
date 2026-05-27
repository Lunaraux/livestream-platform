"""Room model — livestream room with state machine and streamer relation."""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Per 03-room.md: valid room categories
ROOM_CATEGORIES = {
    "game": "游戏",
    "music": "音乐",
    "dance": "舞蹈",
    "chat": "聊天",
    "talent": "才艺",
    "outdoor": "户外",
    "education": "教育",
    "other": "其他",
}

# Room status state machine (03-room.md):
#   idle → live → ended
#   live → banned
#   banned → live (admin unban)
ROOM_STATUSES = ("idle", "live", "ended", "banned")


class Room(TimestampMixin, Base):
    __tablename__ = "rooms"

    __table_args__ = (
        Index("ix_rooms_streamer_id", "streamer_id"),
        Index("ix_rooms_status", "status"),
        Index("ix_rooms_category", "category"),
        Index("ix_rooms_deleted_at", "deleted_at"),
        # One streamer can only have ONE non-deleted room (enforced at service layer)
        Index("ix_rooms_streamer_deleted", "streamer_id", "deleted_at"),
    )

    streamer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # State machine status: idle | live | ended | banned
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")

    # Peak concurrent viewers for the current session (persisted at end)
    peak_viewers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Total number of sessions this room has had
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Current session timing
    started_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    streamer: Mapped["User"] = relationship(
        "User", foreign_keys=[streamer_id], lazy="joined"
    )

    def __repr__(self) -> str:
        return (
            f"<Room id={self.id} title={self.title!r} "
            f"status={self.status!r} streamer_id={self.streamer_id}>"
        )
