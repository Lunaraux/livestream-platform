"""User model — audience, streamer, admin."""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Index for soft-delete queries
    __table_args__ = (
        Index("ix_users_deleted_at", "deleted_at"),
        Index("ix_users_username_deleted", "username", "deleted_at"),
    )

    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(20), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Role: audience, streamer, admin
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="audience")

    # Audience level (1-6), from 02-user.md
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Total consumption in fen (for level calculation)
    total_consumed_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Ban status
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ban_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ban_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Streamer verification (from 02-user.md)
    streamer_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Login security
    login_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_login_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Relationships
    wallet: Mapped["Wallet | None"] = relationship(
        "Wallet", back_populates="user", uselist=False, lazy="joined"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


class Wallet(TimestampMixin, Base):
    __tablename__ = "wallets"

    __table_args__ = (
        Index("ix_wallets_user_id", "user_id"),
        Index("ix_wallets_deleted_at", "deleted_at"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Balance in fen (integer) — per 00-global.md currency convention
    balance_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="wallet")

    def __repr__(self) -> str:
        return f"<Wallet id={self.id} user_id={self.user_id} balance_fen={self.balance_fen}>"
