"""Settlement schemas — earnings, withdrawal, platform revenue.

Per 00-global.md:
- All amounts in fen (int)
- Dates returned as ISO 8601 strings (UTC)
- Pagination via PaginatedData
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

from app.models.settlement import MIN_WITHDRAW_FEN


def _ts_to_iso(ts: int | None) -> str | None:
    """Convert UTC timestamp to ISO 8601 string."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ── Earnings Overview ───────────────────────────────────────────────


class StreamerEarningsOverview(BaseModel):
    """GET /api/streamer/earnings response."""

    today_earnings_fen: int = Field(default=0, description="Today's settled earnings")
    month_earnings_fen: int = Field(default=0, description="This month's settled earnings")
    total_earned_fen: int = Field(default=0, description="Historical total earned")
    available_fen: int = Field(default=0, description="Available for withdrawal")
    pending_fen: int = Field(default=0, description="Pending settlement (from active sessions)")
    frozen_fen: int = Field(default=0, description="Frozen in processing withdrawals")


# ── Settlement Bill ─────────────────────────────────────────────────


class SettlementBillInfo(BaseModel):
    """Single settlement bill in earnings detail list."""

    id: int
    room_id: int
    streamer_id: int
    session_id: int
    total_gift_fen: int
    platform_fee_fen: int
    streamer_earn_fen: int
    settled_at: str
    created_at: str

    model_config = {"from_attributes": True}


# ── Withdraw Request ────────────────────────────────────────────────


class WithdrawCreateRequest(BaseModel):
    """POST /api/streamer/withdraw request body."""

    amount_fen: int = Field(
        ..., ge=MIN_WITHDRAW_FEN, description="Withdraw amount in fen (min 10000)"
    )


class WithdrawRequestInfo(BaseModel):
    """Withdraw request in API responses."""

    id: int
    streamer_id: int
    amount_fen: int
    status: str
    reject_reason: str | None = None
    processed_at: str | None = None
    processed_by: int | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class WithdrawRejectRequest(BaseModel):
    """POST /api/admin/withdraw/{id}/reject request body."""

    reject_reason: str = Field(..., min_length=1, max_length=500, description="Rejection reason")

    @model_validator(mode="after")
    def check_reject_reason_not_empty(self):
        if not self.reject_reason.strip():
            raise ValueError("拒绝原因不能为空")
        return self


# ── Platform Revenue ────────────────────────────────────────────────


class DailyRevenueItem(BaseModel):
    """Single day's platform revenue."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    total_gift_fen: int = Field(default=0)
    platform_revenue_fen: int = Field(default=0)
    settlement_count: int = Field(default=0)


class PlatformRevenueResponse(BaseModel):
    """GET /api/admin/platform/revenue response."""

    items: list[DailyRevenueItem] = Field(default_factory=list)
    total_platform_revenue_fen: int = Field(default=0)
    total_gift_fen: int = Field(default=0)
    total_settlements: int = Field(default=0)
