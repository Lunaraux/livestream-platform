"""Currency models — recharge orders and transaction ledger."""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


# ── Recharge tiers ──────────────────────────────────────────────────
# Per 05-currency.md: tier → (recharge_fen, bonus_fen)

RECHARGE_TIERS: dict[int, tuple[int, int]] = {
    1: (600, 0),
    2: (3000, 150),
    3: (6000, 600),
    4: (30000, 6000),
    5: (60000, 18000),
    6: (300000, 120000),
}


# ── Recharge Order ──────────────────────────────────────────────────


class RechargeOrder(TimestampMixin, Base):
    """Recharge order — per 05-currency.md.

    Lifecycle: pending → paid or failed.
    """

    __tablename__ = "recharge_orders"

    __table_args__ = (
        Index("ix_recharge_orders_user_id", "user_id"),
        Index("ix_recharge_orders_order_no", "order_no", unique=True),
        Index("ix_recharge_orders_status", "status"),
        Index("ix_recharge_orders_deleted_at", "deleted_at"),
    )

    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    recharge_fen: Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_fen: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status: pending, paid, failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    paid_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RechargeOrder id={self.id} order_no={self.order_no!r} "
            f"user_id={self.user_id} tier={self.tier} status={self.status!r}>"
        )


# ── Transaction Ledger ──────────────────────────────────────────────


class Transaction(Base):
    """Transaction ledger — per 05-currency.md.

    Records every coin movement with before/after balance snapshots.
    No soft delete — transactions are immutable audit trail.
    """

    __tablename__ = "transactions"

    __table_args__ = (
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_type", "type"),
        Index("ix_transactions_ref_id", "ref_id"),
        Index("ix_transactions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # type: recharge, gift, privilege
    type: Mapped[str] = mapped_column(String(20), nullable=False)

    # amount_fen: positive = income, negative = expense
    amount_fen: Mapped[int] = mapped_column(Integer, nullable=False)

    # Balance snapshots for reconciliation
    balance_before_fen: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after_fen: Mapped[int] = mapped_column(Integer, nullable=False)

    # Reference to related business entity (recharge order id, gift record id, etc.)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} user_id={self.user_id} "
            f"type={self.type!r} amount_fen={self.amount_fen}>"
        )
