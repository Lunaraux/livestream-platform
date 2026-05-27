"""User model — audience, streamer, admin, follow, streamer verification."""

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
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)

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

    # Follow relationships
    following: Mapped[list["Follow"]] = relationship(
        "Follow", foreign_keys="Follow.follower_id", back_populates="follower", lazy="selectin"
    )
    followers: Mapped[list["Follow"]] = relationship(
        "Follow", foreign_keys="Follow.followed_id", back_populates="followed", lazy="selectin"
    )

    # Streamer application
    streamer_application: Mapped["StreamerApplication | None"] = relationship(
        "StreamerApplication",
        foreign_keys="StreamerApplication.user_id",
        back_populates="user",
        uselist=False,
        lazy="selectin",
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


class Follow(TimestampMixin, Base):
    """Follow relationship: follower follows a streamer."""

    __tablename__ = "follows"

    __table_args__ = (
        Index("ix_follows_follower_id", "follower_id"),
        Index("ix_follows_followed_id", "followed_id"),
        Index("ix_follows_follower_followed", "follower_id", "followed_id", unique=True),
        Index("ix_follows_deleted_at", "deleted_at"),
    )

    follower_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    followed_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    follower: Mapped["User"] = relationship("User", foreign_keys=[follower_id], back_populates="following")
    followed: Mapped["User"] = relationship("User", foreign_keys=[followed_id], back_populates="followers")

    def __repr__(self) -> str:
        return f"<Follow id={self.id} follower={self.follower_id} → followed={self.followed_id}>"


class StreamerApplication(TimestampMixin, Base):
    """Streamer verification application — stores real name & masked ID number."""

    __tablename__ = "streamer_applications"

    __table_args__ = (
        Index("ix_streamer_applications_user_id", "user_id"),
        Index("ix_streamer_applications_status", "status"),
        Index("ix_streamer_applications_deleted_at", "deleted_at"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    real_name: Mapped[str] = mapped_column(String(50), nullable=False)
    id_number: Mapped[str] = mapped_column(String(200), nullable=False)  # masked/encrypted

    # Status: pending, approved, rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # Review info
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="streamer_application"
    )
    reviewer: Mapped["User | None"] = relationship(
        "User", foreign_keys=[reviewed_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<StreamerApplication id={self.id} user_id={self.user_id} status={self.status!r}>"
