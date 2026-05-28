"""Wallet API routes — balance, recharge, transaction history.

Per 05-currency.md:
- GET  /api/wallet/balance            Query balance
- POST /api/wallet/recharge           Create recharge order
- POST /api/wallet/recharge/{order_id}/pay  Simulate payment callback
- GET  /api/wallet/recharge-history   Paginated recharge history
- GET  /api/wallet/transactions       Paginated transaction ledger
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUserDep
from app.schemas.common import ApiResponse, PaginatedData, PaginationParams
from app.schemas.currency import (
    RechargeCreateResponse,
    RechargeOrderInfo,
    RechargeRequest,
    TransactionInfo,
    WalletBalanceInfo,
)
from app.services.currency_service import CurrencyService

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


# ── Query balance ───────────────────────────────────────────────────


@router.get("/balance", response_model=ApiResponse[WalletBalanceInfo])
async def get_balance(
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WalletBalanceInfo]:
    """Get wallet balance.

    GET /api/wallet/balance
    - Returns balance_fen (available) and frozen_fen (locked).
    """
    svc = CurrencyService(db)
    wallet = await svc.get_balance(current_user)
    return ApiResponse(code=0, message="success", data=wallet)


# ── Create recharge order ──────────────────────────────────────────


@router.post("/recharge", response_model=ApiResponse[RechargeCreateResponse])
async def create_recharge(
    body: RechargeRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RechargeCreateResponse]:
    """Create a recharge order (tier 1-6).

    POST /api/wallet/recharge
    - tier: 1-6, each tier maps to fixed recharge_fen + bonus_fen.
    - Returns order_id, order_no, total_fen, and a simulated payment_url.
    - Client visits payment_url to complete the payment.

    Error codes: 4002 (invalid tier)
    """
    svc = CurrencyService(db)
    result = await svc.create_recharge_order(current_user, body.tier)
    return ApiResponse(code=0, message="充值订单已创建", data=result)


# ── Simulate payment callback ───────────────────────────────────────


@router.post("/recharge/{order_id}/pay", response_model=ApiResponse[dict])
async def pay_recharge_order(
    order_id: int,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Simulate payment gateway callback — complete the recharge.

    POST /api/wallet/recharge/{order_id}/pay
    - Validates order belongs to user and is pending.
    - Atomically adds balance, marks order paid, creates transaction record.
    - Idempotent: already-paid orders return 4001 error.

    Error codes: 1004 (order not found), 1001 (already paid)
    """
    svc = CurrencyService(db)
    result = await svc.pay_recharge_order(current_user, order_id)
    return ApiResponse(code=0, message="充值成功", data=result)


# ── Recharge history ────────────────────────────────────────────────


@router.get("/recharge-history", response_model=ApiResponse[PaginatedData[RechargeOrderInfo]])
async def get_recharge_history(
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> ApiResponse[PaginatedData[RechargeOrderInfo]]:
    """Get paginated recharge order history.

    GET /api/wallet/recharge-history
    - Supports pagination: ?page=1&page_size=20
    """
    svc = CurrencyService(db)
    result = await svc.get_recharge_history(current_user, pagination)
    return ApiResponse(code=0, message="success", data=result)


# ── Transaction ledger ──────────────────────────────────────────────


@router.get("/transactions", response_model=ApiResponse[PaginatedData[TransactionInfo]])
async def get_transactions(
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
    type: str | None = None,
) -> ApiResponse[PaginatedData[TransactionInfo]]:
    """Get paginated transaction history.

    GET /api/wallet/transactions
    - Supports pagination: ?page=1&page_size=20
    - Optional type filter: ?type=recharge|gift|privilege
    """
    svc = CurrencyService(db)
    result = await svc.get_transactions(current_user, pagination, type_filter=type)
    return ApiResponse(code=0, message="success", data=result)
