"""Currency service — wallet balance, recharge orders, transaction ledger."""

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InsufficientBalanceError,
    InvalidRechargeAmountError,
    NotFoundError,
    RechargeOrderAlreadyPaidError,
    RechargeOrderNotFoundError,
)
from app.models.currency import RECHARGE_TIERS, RechargeOrder, Transaction
from app.models.user import User, Wallet
from app.schemas.common import PaginatedData, PaginationParams
from app.schemas.currency import (
    RechargeCreateResponse,
    RechargeOrderInfo,
    TransactionInfo,
    WalletBalanceInfo,
)


def _now_ts() -> int:
    return int(time.time())


def _ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _generate_order_no() -> str:
    """Generate a unique recharge order number."""
    timestamp_part = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    random_part = uuid.uuid4().hex[:8].upper()
    return f"RC{timestamp_part}{random_part}"


class CurrencyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Get wallet balance ──────────────────────────────────────────

    async def get_balance(self, user: User) -> WalletBalanceInfo:
        """Return the user's wallet balance and frozen amount.

        Creates a wallet if one doesn't exist (belt-and-suspenders).
        """
        result = await self.db.execute(
            select(Wallet).where(
                Wallet.user_id == user.id, Wallet.deleted_at.is_(None)
            )
        )
        wallet = result.scalar_one_or_none()

        if wallet is None:
            # Create wallet on-the-fly (should not happen, but safe)
            now = _now_ts()
            wallet = Wallet(
                user_id=user.id,
                balance_fen=0,
                frozen_fen=0,
                created_at=now,
                updated_at=now,
            )
            self.db.add(wallet)
            await self.db.flush()

        return WalletBalanceInfo(
            balance_fen=wallet.balance_fen,
            frozen_fen=wallet.frozen_fen,
        )

    # ── Create recharge order ───────────────────────────────────────

    async def create_recharge_order(self, user: User, tier: int) -> RechargeCreateResponse:
        """Create a pending recharge order and return simulated payment info.

        Per 05-currency.md:
        - tier must be 1-6
        - recharge_fen + bonus_fen = total_fen
        - Returns a simulated payment URL

        Raises:
            InvalidRechargeAmountError (4002): tier not in RECHARGE_TIERS.
        """
        if tier not in RECHARGE_TIERS:
            raise InvalidRechargeAmountError()

        recharge_fen, bonus_fen = RECHARGE_TIERS[tier]
        total_fen = recharge_fen + bonus_fen

        now = _now_ts()
        order = RechargeOrder(
            order_no=_generate_order_no(),
            user_id=user.id,
            tier=tier,
            recharge_fen=recharge_fen,
            bonus_fen=bonus_fen,
            total_fen=total_fen,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self.db.add(order)
        await self.db.flush()

        return RechargeCreateResponse(
            order_id=order.id,
            order_no=order.order_no,
            total_fen=total_fen,
            payment_url=f"/api/wallet/recharge/{order.id}/pay",
        )

    # ── Pay recharge order (simulated callback) ─────────────────────

    async def pay_recharge_order(self, user: User, order_id: int) -> dict:
        """Simulate payment gateway callback — complete the recharge.

        Per 05-currency.md:
        - Validates order belongs to user and is pending
        - Atomically updates balance and creates transaction record
        - All operations in a single transaction (caller's db session)

        Raises:
            RechargeOrderNotFoundError: order not found or not owned by user.
            RechargeOrderAlreadyPaidError: order already paid.
        """
        result = await self.db.execute(
            select(RechargeOrder).where(
                RechargeOrder.id == order_id,
                RechargeOrder.user_id == user.id,
            )
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise RechargeOrderNotFoundError()

        if order.status != "pending":
            raise RechargeOrderAlreadyPaidError()

        # Get wallet (create if not exists)
        wallet_result = await self.db.execute(
            select(Wallet).where(
                Wallet.user_id == user.id, Wallet.deleted_at.is_(None)
            )
        )
        wallet = wallet_result.scalar_one_or_none()

        now = _now_ts()
        if wallet is None:
            wallet = Wallet(
                user_id=user.id,
                balance_fen=0,
                frozen_fen=0,
                created_at=now,
                updated_at=now,
            )
            self.db.add(wallet)
            await self.db.flush()

        # Atomic balance update
        balance_before = wallet.balance_fen
        wallet.balance_fen += order.total_fen
        wallet.updated_at = now

        # Mark order as paid
        order.status = "paid"
        order.paid_at = now
        order.updated_at = now

        # Create transaction record
        txn = Transaction(
            user_id=user.id,
            type="recharge",
            amount_fen=order.total_fen,  # positive = income
            balance_before_fen=balance_before,
            balance_after_fen=wallet.balance_fen,
            ref_id=order.id,
            description=f"充值 tier={order.tier} ({order.recharge_fen // 100}元 → {order.total_fen // 100}金币)",
            created_at=now,
        )
        self.db.add(txn)
        await self.db.flush()

        return {
            "order_id": order.id,
            "order_no": order.order_no,
            "status": "paid",
            "total_fen": order.total_fen,
            "balance_fen": wallet.balance_fen,
        }

    # ── Recharge history ────────────────────────────────────────────

    async def get_recharge_history(
        self, user: User, pagination: PaginationParams
    ) -> PaginatedData[RechargeOrderInfo]:
        """Return paginated recharge order history for the user."""
        offset = (pagination.page - 1) * pagination.page_size

        total = await self.db.scalar(
            select(func.count(RechargeOrder.id)).where(
                RechargeOrder.user_id == user.id,
            )
        )

        query = (
            select(RechargeOrder)
            .where(RechargeOrder.user_id == user.id)
            .order_by(RechargeOrder.id.desc())
            .offset(offset)
            .limit(pagination.page_size)
        )
        orders = (await self.db.execute(query)).scalars().all()

        items = [
            RechargeOrderInfo(
                id=o.id,
                order_no=o.order_no,
                user_id=o.user_id,
                tier=o.tier,
                recharge_fen=o.recharge_fen,
                bonus_fen=o.bonus_fen,
                total_fen=o.total_fen,
                status=o.status,
                paid_at=_ts_to_iso(o.paid_at) if o.paid_at else None,
                created_at=_ts_to_iso(o.created_at),
                updated_at=_ts_to_iso(o.updated_at),
            )
            for o in orders
        ]

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    # ── Transaction ledger ──────────────────────────────────────────

    async def get_transactions(
        self,
        user: User,
        pagination: PaginationParams,
        type_filter: str | None = None,
    ) -> PaginatedData[TransactionInfo]:
        """Return paginated transaction history, optionally filtered by type.

        type_filter: None (all), "recharge", "gift", or "privilege".
        """
        offset = (pagination.page - 1) * pagination.page_size

        conditions = [Transaction.user_id == user.id]
        if type_filter:
            conditions.append(Transaction.type == type_filter)

        total = await self.db.scalar(
            select(func.count(Transaction.id)).where(*conditions)
        )

        query = (
            select(Transaction)
            .where(*conditions)
            .order_by(Transaction.id.desc())
            .offset(offset)
            .limit(pagination.page_size)
        )
        txns = (await self.db.execute(query)).scalars().all()

        items = [
            TransactionInfo(
                id=t.id,
                user_id=t.user_id,
                type=t.type,
                amount_fen=t.amount_fen,
                balance_before_fen=t.balance_before_fen,
                balance_after_fen=t.balance_after_fen,
                ref_id=t.ref_id,
                description=t.description,
                created_at=_ts_to_iso(t.created_at),
            )
            for t in txns
        ]

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )
