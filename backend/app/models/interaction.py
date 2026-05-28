"""Interaction models — Danmaku, Gift, GiftRecord, ForbiddenWord."""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# ── Danmaku color constants ───────────────────────────────────────

# Colors available per level (HEX)
DANMAKU_COLORS_BY_LEVEL: dict[int, set[str]] = {
    1: {"#FFFFFF"},                          # white only
    2: {"#FFFFFF"},                          # white only
    3: {"#FFFFFF"},                          # white only
    4: {"#FFFFFF", "#808080"},               # white, grey
    5: {"#FFFFFF", "#808080", "#CD7F32"},    # white, grey, bronze
    6: {"#FFFFFF", "#808080", "#CD7F32", "#C0C0C0", "#FFD700"},  # +silver, gold
}

# Diamond-level (level >= 7 or special tier): any color + pin support
DIAMOND_LEVEL_THRESHOLD = 7
MAX_PIN_DURATION_SECONDS = 30

# All valid colors (for validation)
ALL_VALID_COLORS: set[str] = {
    "#FFFFFF", "#808080", "#CD7F32", "#C0C0C0", "#FFD700",
    "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF",
    "#00FFFF", "#FFA500", "#800080", "#008000", "#000080",
}


def get_allowed_colors(level: int) -> set[str]:
    """Return the set of colors allowed for a given user level."""
    if level >= DIAMOND_LEVEL_THRESHOLD:
        return ALL_VALID_COLORS
    return DANMAKU_COLORS_BY_LEVEL.get(level, {"#FFFFFF"})


# ── Gift effect types ─────────────────────────────────────────────

GIFT_EFFECTS = {
    "normal": "普通动画",
    "fullscreen": "全屏特效",
    "announcement": "全屏特效+公告",
    "guardian": "月度守护特效",
}

# ── Models ────────────────────────────────────────────────────────


class Danmaku(TimestampMixin, Base):
    """Danmaku (bullet comment) sent by a user in a room."""

    __tablename__ = "danmaku"

    __table_args__ = (
        Index("ix_danmaku_room_id", "room_id"),
        Index("ix_danmaku_user_id", "user_id"),
        Index("ix_danmaku_room_created", "room_id", "created_at"),
        Index("ix_danmaku_deleted_at", "deleted_at"),
    )

    room_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#FFFFFF")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pin_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    room: Mapped["Room"] = relationship("Room", lazy="selectin")
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Danmaku id={self.id} room_id={self.room_id} "
            f"user_id={self.user_id} content={self.content[:20]!r}>"
        )


class Gift(TimestampMixin, Base):
    """Platform preset gift catalog. Managed by admin."""

    __tablename__ = "gifts"

    __table_args__ = (
        Index("ix_gifts_deleted_at", "deleted_at"),
    )

    name: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    price_fen: Mapped[int] = mapped_column(Integer, nullable=False)
    effect: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return (
            f"<Gift id={self.id} name={self.name!r} "
            f"price_fen={self.price_fen} effect={self.effect!r}>"
        )


class GiftRecord(TimestampMixin, Base):
    """Record of a gift sent during a livestream session."""

    __tablename__ = "gift_records"

    __table_args__ = (
        Index("ix_gift_records_room_id", "room_id"),
        Index("ix_gift_records_sender_id", "sender_id"),
        Index("ix_gift_records_receiver_id", "receiver_id"),
        Index("ix_gift_records_room_sender", "room_id", "sender_id"),
        Index("ix_gift_records_deleted_at", "deleted_at"),
    )

    room_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receiver_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gift_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("gifts.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_amount_fen: Mapped[int] = mapped_column(Integer, nullable=False)
    # Per-user consumption tracking for level calculation
    gift_name: Mapped[str] = mapped_column(String(20), nullable=False)
    gift_effect: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")

    # Relationships
    room: Mapped["Room"] = relationship(
        "Room", foreign_keys=[room_id], lazy="selectin"
    )
    sender: Mapped["User"] = relationship(
        "User", foreign_keys=[sender_id], lazy="selectin"
    )
    receiver: Mapped["User"] = relationship(
        "User", foreign_keys=[receiver_id], lazy="selectin"
    )
    gift: Mapped["Gift"] = relationship(
        "Gift", foreign_keys=[gift_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<GiftRecord id={self.id} room_id={self.room_id} "
            f"sender_id={self.sender_id} gift_name={self.gift_name!r} "
            f"quantity={self.quantity}>"
        )


class ForbiddenWord(TimestampMixin, Base):
    """Forbidden word / banned keyword for danmaku content filtering."""

    __tablename__ = "forbidden_words"

    __table_args__ = (
        Index("ix_forbidden_words_word", "word"),
        Index("ix_forbidden_words_deleted_at", "deleted_at"),
    )

    word: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    def __repr__(self) -> str:
        return f"<ForbiddenWord id={self.id} word={self.word!r}>"
