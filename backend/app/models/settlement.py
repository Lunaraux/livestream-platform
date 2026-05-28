"""Settlement models — streamer wallet, settlement bills, withdraw requests.

Per 06-settlement.md:
- Platform commission: 30% (stored as integer 30)
- Streamer share: 70%
- Min withdraw: 10000 fen (100 yuan)
"""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# ── Commission rate ─────────────────────────────────────────────────

PLATFORM_COMMISSION_PCT = 30  # platform takes 30%, streamer gets 70%
MIN_WITHDRAW_FEN = 10000  # minimum withdraw amount in fen (100 yuan)


# ── Streamer Wallet ─────────────────────────────────────────────────


class StreamerWallet(TimestampMixin, Base):
    """Per-streamer earnings wallet.

    Tracks earnings lifecycle: pending → available → withdrawn.
    Separate from user Wallet (which holds recharge coin balance).
    """

    __tablename__ = "streamer_wallets"

    __table_args__ = (
        Index("ix_streamer_wallets_streamer_id", "streamer_id", unique=True),
        Index("ix_streamer_wallets_deleted_at", "deleted_at"),
    )

    streamer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Pending settlement (gifts received but not yet settled)
    pending_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Available for withdrawal (settled, not yet withdrawn)
    available_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Frozen during withdrawal processing
    frozen_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Historical total earned (monotonically increasing)
    total_earned_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    streamer: Mapped["User"] = relationship(
        "User", foreign_keys=[streamer_id], lazy="joined"
    )

    def __repr__(self) -> str:
        return (
            f"<StreamerWallet id={self.id} streamer_id={self.streamer_id} "
            f"available_fen={self.available_fen} pending_fen={self.pending_fen}>"
        )


# ── Settlement Bill ─────────────────────────────────────────────────


class SettlementBill(TimestampMixin, Base):
    """Settlement bill for a completed livestream session.

    Generated when a room session ends (manual stop or auto-settle at 2am).
    Records the gift revenue split for one session.
    """

    __tablename__ = "settlement_bills"

    __table_args__ = (
        Index("ix_settlement_bills_room_id", "room_id"),
        Index("ix_settlement_bills_streamer_id", "streamer_id"),
        Index("ix_settlement_bills_settled_at", "settled_at"),
        Index("ix_settlement_bills_streamer_settled", "streamer_id", "settled_at"),
        Index("ix_settlement_bills_deleted_at", "deleted_at"),
    )

    room_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    streamer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Session number within the room (1-based)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Total gift value in this session (fen)
    total_gift_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Platform commission (fen)
    platform_fee_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Streamer earnings for this session (fen)
    streamer_earn_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # When this bill was settled (UTC timestamp)
    settled_at: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    room: Mapped["Room"] = relationship("Room", foreign_keys=[room_id], lazy="selectin")
    streamer: Mapped["User"] = relationship(
        "User", foreign_keys=[streamer_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<SettlementBill id={self.id} room_id={self.room_id} "
            f"session_id={self.session_id} streamer_earn_fen={self.streamer_earn_fen}>"
        )


# ── Withdraw Request ────────────────────────────────────────────────


class WithdrawRequest(TimestampMixin, Base):
    """Withdrawal request submitted by a streamer.

    Lifecycle: pending → approved | rejected.
    - pending: awaiting admin review, amount frozen in streamer wallet
    - approved: admin approved, amount deducted from available, frozen released
    - rejected: admin rejected, frozen amount returned to available
    """

    __tablename__ = "withdraw_requests"

    __table_args__ = (
        Index("ix_withdraw_requests_streamer_id", "streamer_id"),
        Index("ix_withdraw_requests_status", "status"),
        Index("ix_withdraw_requests_streamer_status", "streamer_id", "status"),
        Index("ix_withdraw_requests_deleted_at", "deleted_at"),
    )

    streamer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Withdrawal amount in fen
    amount_fen: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status: pending, approved, rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # Rejection reason (only for rejected)
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # When the admin processed this request (UTC timestamp)
    processed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Who processed (admin user id)
    processed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    streamer: Mapped["User"] = relationship(
        "User", foreign_keys=[streamer_id], lazy="selectin"
    )
    processor: Mapped["User | None"] = relationship(
        "User", foreign_keys=[processed_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<WithdrawRequest id={self.id} streamer_id={self.streamer_id} "
            f"amount_fen={self.amount_fen} status={self.status!r}>"
        )
