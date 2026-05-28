"""Settlement API routes — streamer earnings and admin withdrawal management.

Per 06-settlement.md:

Streamer routes (require streamer role):
  GET  /api/streamer/earnings           Earnings overview
  GET  /api/streamer/earnings/detail    Earnings detail (paginated, date filter)
  POST /api/streamer/withdraw           Submit withdrawal request
  GET  /api/streamer/withdraw-history   Withdrawal history (paginated)

Admin routes (require admin role):
  POST /api/admin/withdraw/{id}/approve  Approve withdrawal
  POST /api/admin/withdraw/{id}/reject   Reject withdrawal
  GET  /api/admin/platform/revenue       Platform revenue stats
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUserDep, require_role
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedData, PaginationParams
from app.schemas.settlement import (
    PlatformRevenueResponse,
    SettlementBillInfo,
    StreamerEarningsOverview,
    WithdrawCreateRequest,
    WithdrawRejectRequest,
    WithdrawRequestInfo,
)
from app.services.settlement_service import SettlementService

streamer_router = APIRouter(prefix="/api/streamer", tags=["settlement"])

admin_router = APIRouter(prefix="/api/admin", tags=["settlement-admin"])


# ══════════════════════════════════════════════════════════════════════════
# Streamer routes
# ══════════════════════════════════════════════════════════════════════════


# ── Earnings overview ───────────────────────────────────────────────


@streamer_router.get(
    "/earnings", response_model=ApiResponse[StreamerEarningsOverview]
)
async def get_earnings_overview(
    current_user: User = Depends(require_role("streamer", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[StreamerEarningsOverview]:
    """Get streamer earnings overview.

    GET /api/streamer/earnings
    - Returns today's earnings, monthly earnings, total earned,
      available balance, pending balance, and frozen balance.
    """
    svc = SettlementService(db)
    data = await svc.get_earnings_overview(current_user)
    return ApiResponse(code=0, message="success", data=data)


# ── Earnings detail ─────────────────────────────────────────────────


@streamer_router.get(
    "/earnings/detail", response_model=ApiResponse[PaginatedData[SettlementBillInfo]]
)
async def get_earnings_detail(
    current_user: User = Depends(require_role("streamer", "admin")),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
    start_date: str | None = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str | None = Query(None, description="End date YYYY-MM-DD"),
) -> ApiResponse[PaginatedData[SettlementBillInfo]]:
    """Get paginated earnings detail (settlement bills).

    GET /api/streamer/earnings/detail
    - Supports pagination: ?page=1&page_size=20
    - Optional date range: ?start_date=2024-01-01&end_date=2024-01-31
    """
    svc = SettlementService(db)
    data = await svc.get_earnings_detail(
        current_user, pagination, start_date=start_date, end_date=end_date
    )
    return ApiResponse(code=0, message="success", data=data)


# ── Withdraw ────────────────────────────────────────────────────────


@streamer_router.post(
    "/withdraw", response_model=ApiResponse[WithdrawRequestInfo]
)
async def create_withdraw(
    body: WithdrawCreateRequest,
    current_user: User = Depends(require_role("streamer")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawRequestInfo]:
    """Submit a withdrawal request.

    POST /api/streamer/withdraw
    - amount_fen: withdrawal amount in fen (minimum 10000 = 100 yuan)
    - Freezes the amount on creation.
    - Only one pending withdrawal per streamer.

    Error codes: 5001 (below minimum), 4001 (insufficient balance), 5002 (pending exists)
    """
    svc = SettlementService(db)
    data = await svc.create_withdraw(current_user, body.amount_fen)
    return ApiResponse(code=0, message="提现申请已提交", data=data)


# ── Withdraw history ────────────────────────────────────────────────


@streamer_router.get(
    "/withdraw-history", response_model=ApiResponse[PaginatedData[WithdrawRequestInfo]]
)
async def get_withdraw_history(
    current_user: User = Depends(require_role("streamer")),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> ApiResponse[PaginatedData[WithdrawRequestInfo]]:
    """Get paginated withdrawal history.

    GET /api/streamer/withdraw-history
    - Supports pagination: ?page=1&page_size=20
    """
    svc = SettlementService(db)
    data = await svc.get_withdraw_history(current_user, pagination)
    return ApiResponse(code=0, message="success", data=data)


# ══════════════════════════════════════════════════════════════════════════
# Admin routes
# ══════════════════════════════════════════════════════════════════════════


# ── Approve withdrawal ──────────────────────────────────────────────


@admin_router.post(
    "/withdraw/{withdraw_id}/approve", response_model=ApiResponse[WithdrawRequestInfo]
)
async def approve_withdraw(
    withdraw_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawRequestInfo]:
    """Approve a withdrawal request (admin only).

    POST /api/admin/withdraw/{id}/approve
    - Releases frozen amount and marks as approved.
    - Simulates fund transfer.

    Error codes: 1004 (not found), 1001 (already processed)
    """
    svc = SettlementService(db)
    data = await svc.approve_withdraw(withdraw_id, current_user)
    return ApiResponse(code=0, message="提现已批准", data=data)


# ── Reject withdrawal ───────────────────────────────────────────────


@admin_router.post(
    "/withdraw/{withdraw_id}/reject", response_model=ApiResponse[WithdrawRequestInfo]
)
async def reject_withdraw(
    withdraw_id: int,
    body: WithdrawRejectRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawRequestInfo]:
    """Reject a withdrawal request (admin only).

    POST /api/admin/withdraw/{id}/reject
    - Returns frozen amount to available balance.
    - Must provide a rejection reason.

    Error codes: 1004 (not found), 1001 (already processed)
    """
    svc = SettlementService(db)
    data = await svc.reject_withdraw(withdraw_id, current_user, body.reject_reason)
    return ApiResponse(code=0, message="提现已拒绝", data=data)


# ── Platform revenue ────────────────────────────────────────────────


@admin_router.get(
    "/platform/revenue", response_model=ApiResponse[PlatformRevenueResponse]
)
async def get_platform_revenue(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    start_date: str | None = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str | None = Query(None, description="End date YYYY-MM-DD"),
) -> ApiResponse[PlatformRevenueResponse]:
    """Get platform revenue statistics (admin only).

    GET /api/admin/platform/revenue
    - Returns daily revenue grouped by date.
    - Optional date range: ?start_date=2024-01-01&end_date=2024-01-31
    - Defaults to last 30 days if no range provided.
    """
    svc = SettlementService(db)
    data = await svc.get_platform_revenue(start_date=start_date, end_date=end_date)
    return ApiResponse(code=0, message="success", data=data)
