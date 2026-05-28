"""Currency schemas — wallet balance, recharge, transaction request/response models."""

from pydantic import BaseModel, Field


# ── Wallet balance ──────────────────────────────────────────────────


class WalletBalanceInfo(BaseModel):
    """Wallet balance response — per 05-currency.md."""

    balance_fen: int = Field(..., description="Available balance in fen")
    frozen_fen: int = Field(..., description="Frozen balance in fen")

    model_config = {"from_attributes": True}


# ── Recharge ────────────────────────────────────────────────────────


class RechargeRequest(BaseModel):
    """Recharge request — select a tier."""

    tier: int = Field(..., ge=1, le=6, description="Recharge tier (1-6)")


class RechargeOrderInfo(BaseModel):
    """Recharge order details in API responses."""

    id: int
    order_no: str
    user_id: int
    tier: int
    recharge_fen: int
    bonus_fen: int
    total_fen: int
    status: str
    paid_at: str | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class RechargeCreateResponse(BaseModel):
    """Response after creating a recharge order (before payment)."""

    order_id: int
    order_no: str
    total_fen: int
    payment_url: str


# ── Transaction ─────────────────────────────────────────────────────


class TransactionInfo(BaseModel):
    """Transaction ledger entry in API responses."""

    id: int
    user_id: int
    type: str
    amount_fen: int
    balance_before_fen: int
    balance_after_fen: int
    ref_id: int | None = None
    description: str | None = None
    created_at: str

    model_config = {"from_attributes": True}
