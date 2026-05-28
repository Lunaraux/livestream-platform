"""Settlement service — streamer earnings, settlement bills, withdrawal flow.

Per 06-settlement.md:
- Platform commission: PLATFORM_COMMISSION_PCT (30%)
- Streamer share: floor(total_gift_fen * 70 / 100)
- Min withdraw: MIN_WITHDRAW_FEN (10000 fen = 100 yuan)
- Only one pending withdraw per streamer at a time

Settlement lifecycle:
  gifts in session → pending in streamer_wallet
  room ends / auto-settle → settlement_bill created, pending → available
  streamer withdraws → available → frozen
  admin approves → frozen released, available deducted
  admin rejects → frozen → available
"""

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InsufficientAvailableBalanceError,
    WithdrawAlreadyProcessedError,
    WithdrawAmountTooLowError,
    WithdrawPendingError,
    WithdrawRequestNotFoundError,
)
from app.models.settlement import (
    MIN_WITHDRAW_FEN,
    PLATFORM_COMMISSION_PCT,
    SettlementBill,
    StreamerWallet,
    WithdrawRequest,
)
from app.models.user import User
from app.schemas.common import PaginatedData, PaginationParams
from app.schemas.settlement import (
    DailyRevenueItem,
    PlatformRevenueResponse,
    SettlementBillInfo,
    StreamerEarningsOverview,
    WithdrawRequestInfo,
)


def _now_ts() -> int:
    return int(time.time())


def _ts_to_iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _today_range() -> tuple[int, int]:
    """Return (start_ts, end_ts) for today in UTC."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _month_range() -> tuple[int, int]:
    """Return (start_ts, end_ts) for current month in UTC."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return int(start.timestamp()), int(end.timestamp())


def _date_to_ts_range(date_str: str | None) -> tuple[int | None, int | None]:
    """Convert ISO date string (YYYY-MM-DD) to UTC timestamp range.
    Returns (start_of_day_ts, start_of_next_day_ts) or (None, None).
    """
    if not date_str:
        return None, None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start = int(dt.timestamp())
        end = int((dt + timedelta(days=1)).timestamp())
        return start, end
    except ValueError:
        return None, None


class SettlementService:
    """Streamer earnings and withdrawal business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Wallet helpers ──────────────────────────────────────────────

    async def _get_or_create_wallet(self, streamer_id: int) -> StreamerWallet:
        """Get the streamer's earnings wallet, creating if not exists."""
        result = await self.db.execute(
            select(StreamerWallet).where(
                StreamerWallet.streamer_id == streamer_id,
                StreamerWallet.deleted_at.is_(None),
            )
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            now = _now_ts()
            wallet = StreamerWallet(
                streamer_id=streamer_id,
                pending_fen=0,
                available_fen=0,
                frozen_fen=0,
                total_earned_fen=0,
                created_at=now,
                updated_at=now,
            )
            self.db.add(wallet)
            await self.db.flush()
        return wallet

    # ── Earnings overview ───────────────────────────────────────────

    async def get_earnings_overview(
        self, streamer: User
    ) -> StreamerEarningsOverview:
        """Return daily/monthly/total earnings and wallet balances."""
        wallet = await self._get_or_create_wallet(streamer.id)

        today_start, today_end = _today_range()
        month_start, month_end = _month_range()

        # Today's settled earnings
        today_earnings = await self.db.scalar(
            select(func.coalesce(func.sum(SettlementBill.streamer_earn_fen), 0)).where(
                SettlementBill.streamer_id == streamer.id,
                SettlementBill.settled_at >= today_start,
                SettlementBill.settled_at < today_end,
                SettlementBill.deleted_at.is_(None),
            )
        ) or 0

        # This month's settled earnings
        month_earnings = await self.db.scalar(
            select(func.coalesce(func.sum(SettlementBill.streamer_earn_fen), 0)).where(
                SettlementBill.streamer_id == streamer.id,
                SettlementBill.settled_at >= month_start,
                SettlementBill.settled_at < month_end,
                SettlementBill.deleted_at.is_(None),
            )
        ) or 0

        return StreamerEarningsOverview(
            today_earnings_fen=today_earnings,
            month_earnings_fen=month_earnings,
            total_earned_fen=wallet.total_earned_fen,
            available_fen=wallet.available_fen,
            pending_fen=wallet.pending_fen,
            frozen_fen=wallet.frozen_fen,
        )

    # ── Earnings detail ─────────────────────────────────────────────

    async def get_earnings_detail(
        self,
        streamer: User,
        pagination: PaginationParams,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> PaginatedData[SettlementBillInfo]:
        """Return paginated settlement bills, optionally filtered by date range."""
        offset = (pagination.page - 1) * pagination.page_size

        conditions = [
            SettlementBill.streamer_id == streamer.id,
            SettlementBill.deleted_at.is_(None),
        ]

        start_ts, end_ts_start = _date_to_ts_range(start_date)
        if start_ts is not None:
            conditions.append(SettlementBill.settled_at >= start_ts)

        end_ts, _ = _date_to_ts_range(end_date)
        if end_ts is not None:
            conditions.append(SettlementBill.settled_at < end_ts)

        total = await self.db.scalar(
            select(func.count(SettlementBill.id)).where(*conditions)
        )

        query = (
            select(SettlementBill)
            .where(*conditions)
            .order_by(SettlementBill.settled_at.desc())
            .offset(offset)
            .limit(pagination.page_size)
        )
        bills = (await self.db.execute(query)).scalars().all()

        items = [
            SettlementBillInfo(
                id=b.id,
                room_id=b.room_id,
                streamer_id=b.streamer_id,
                session_id=b.session_id,
                total_gift_fen=b.total_gift_fen,
                platform_fee_fen=b.platform_fee_fen,
                streamer_earn_fen=b.streamer_earn_fen,
                settled_at=_ts_to_iso(b.settled_at),
                created_at=_ts_to_iso(b.created_at),
            )
            for b in bills
        ]

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    # ── Create withdraw request ─────────────────────────────────────

    async def create_withdraw(
        self, streamer: User, amount_fen: int
    ) -> WithdrawRequestInfo:
        """Submit a withdrawal request.

        Rules per 06-settlement.md:
        - Minimum withdrawal: MIN_WITHDRAW_FEN (10000 fen)
        - Available balance must be sufficient
        - Only one pending withdrawal at a time (error 5002)
        - Freezes the amount on creation

        Raises:
            WithdrawAmountTooLowError (5001): below minimum
            InsufficientAvailableBalanceError (4001): not enough available
            WithdrawPendingError (5002): already have pending request
        """
        if amount_fen < MIN_WITHDRAW_FEN:
            raise WithdrawAmountTooLowError()

        wallet = await self._get_or_create_wallet(streamer.id)

        if wallet.available_fen < amount_fen:
            raise InsufficientAvailableBalanceError()

        # Check for existing pending withdrawal
        existing = await self.db.scalar(
            select(func.count(WithdrawRequest.id)).where(
                WithdrawRequest.streamer_id == streamer.id,
                WithdrawRequest.status == "pending",
                WithdrawRequest.deleted_at.is_(None),
            )
        )
        if existing and existing > 0:
            raise WithdrawPendingError()

        now = _now_ts()

        # Freeze the amount
        wallet.available_fen -= amount_fen
        wallet.frozen_fen += amount_fen
        wallet.updated_at = now

        # Create withdraw request
        wr = WithdrawRequest(
            streamer_id=streamer.id,
            amount_fen=amount_fen,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self.db.add(wr)
        await self.db.flush()

        return WithdrawRequestInfo(
            id=wr.id,
            streamer_id=wr.streamer_id,
            amount_fen=wr.amount_fen,
            status=wr.status,
            reject_reason=None,
            processed_at=None,
            processed_by=None,
            created_at=_ts_to_iso(wr.created_at),
            updated_at=_ts_to_iso(wr.updated_at),
        )

    # ── Withdraw history ────────────────────────────────────────────

    async def get_withdraw_history(
        self, streamer: User, pagination: PaginationParams
    ) -> PaginatedData[WithdrawRequestInfo]:
        """Return paginated withdrawal history for a streamer."""
        offset = (pagination.page - 1) * pagination.page_size

        total = await self.db.scalar(
            select(func.count(WithdrawRequest.id)).where(
                WithdrawRequest.streamer_id == streamer.id,
                WithdrawRequest.deleted_at.is_(None),
            )
        )

        query = (
            select(WithdrawRequest)
            .where(
                WithdrawRequest.streamer_id == streamer.id,
                WithdrawRequest.deleted_at.is_(None),
            )
            .order_by(WithdrawRequest.id.desc())
            .offset(offset)
            .limit(pagination.page_size)
        )
        requests = (await self.db.execute(query)).scalars().all()

        items = [
            WithdrawRequestInfo(
                id=r.id,
                streamer_id=r.streamer_id,
                amount_fen=r.amount_fen,
                status=r.status,
                reject_reason=r.reject_reason,
                processed_at=_ts_to_iso(r.processed_at),
                processed_by=r.processed_by,
                created_at=_ts_to_iso(r.created_at),
                updated_at=_ts_to_iso(r.updated_at),
            )
            for r in requests
        ]

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    # ── Admin: approve withdrawal ───────────────────────────────────

    async def approve_withdraw(
        self, withdraw_id: int, admin: User
    ) -> WithdrawRequestInfo:
        """Approve a withdrawal request.

        Actions:
        - Release frozen amount from wallet
        - Deduct from available (already moved to frozen at creation)
        - Mark as approved

        Raises:
            WithdrawRequestNotFoundError: not found
            WithdrawAlreadyProcessedError: already approved/rejected
        """
        result = await self.db.execute(
            select(WithdrawRequest).where(
                WithdrawRequest.id == withdraw_id,
                WithdrawRequest.deleted_at.is_(None),
            )
        )
        wr = result.scalar_one_or_none()
        if wr is None:
            raise WithdrawRequestNotFoundError()

        if wr.status != "pending":
            raise WithdrawAlreadyProcessedError()

        wallet = await self._get_or_create_wallet(wr.streamer_id)
        now = _now_ts()

        # Release frozen amount (the available was already reduced at withdrawal creation)
        wallet.frozen_fen -= wr.amount_fen
        wallet.updated_at = now

        # Mark as approved
        wr.status = "approved"
        wr.processed_at = now
        wr.processed_by = admin.id
        wr.updated_at = now
        await self.db.flush()

        return WithdrawRequestInfo(
            id=wr.id,
            streamer_id=wr.streamer_id,
            amount_fen=wr.amount_fen,
            status=wr.status,
            reject_reason=None,
            processed_at=_ts_to_iso(wr.processed_at),
            processed_by=wr.processed_by,
            created_at=_ts_to_iso(wr.created_at),
            updated_at=_ts_to_iso(wr.updated_at),
        )

    # ── Admin: reject withdrawal ────────────────────────────────────

    async def reject_withdraw(
        self, withdraw_id: int, admin: User, reject_reason: str
    ) -> WithdrawRequestInfo:
        """Reject a withdrawal request.

        Actions:
        - Release frozen amount back to available
        - Mark as rejected with reason

        Raises:
            WithdrawRequestNotFoundError: not found
            WithdrawAlreadyProcessedError: already approved/rejected
        """
        result = await self.db.execute(
            select(WithdrawRequest).where(
                WithdrawRequest.id == withdraw_id,
                WithdrawRequest.deleted_at.is_(None),
            )
        )
        wr = result.scalar_one_or_none()
        if wr is None:
            raise WithdrawRequestNotFoundError()

        if wr.status != "pending":
            raise WithdrawAlreadyProcessedError()

        wallet = await self._get_or_create_wallet(wr.streamer_id)
        now = _now_ts()

        # Return frozen amount to available
        wallet.frozen_fen -= wr.amount_fen
        wallet.available_fen += wr.amount_fen
        wallet.updated_at = now

        # Mark as rejected
        wr.status = "rejected"
        wr.reject_reason = reject_reason
        wr.processed_at = now
        wr.processed_by = admin.id
        wr.updated_at = now
        await self.db.flush()

        return WithdrawRequestInfo(
            id=wr.id,
            streamer_id=wr.streamer_id,
            amount_fen=wr.amount_fen,
            status=wr.status,
            reject_reason=wr.reject_reason,
            processed_at=_ts_to_iso(wr.processed_at),
            processed_by=wr.processed_by,
            created_at=_ts_to_iso(wr.created_at),
            updated_at=_ts_to_iso(wr.updated_at),
        )

    # ── Settlement trigger ──────────────────────────────────────────

    async def settle_room_session(
        self, room_id: int, streamer_id: int, session_id: int
    ) -> SettlementBillInfo | None:
        """Settle a completed room session.

        Called when a room session ends (manual stop or auto-settle).
        Aggregates all gift records for the room and creates a settlement bill.

        Returns the settlement bill info, or None if no gifts to settle.
        """
        from app.models.interaction import GiftRecord

        # Sum all gift records for this room (non-deleted, during the session)
        total_gift_fen = await self.db.scalar(
            select(func.coalesce(func.sum(GiftRecord.total_amount_fen), 0)).where(
                GiftRecord.room_id == room_id,
                GiftRecord.receiver_id == streamer_id,
                GiftRecord.deleted_at.is_(None),
            )
        ) or 0

        # If there are also gifts in earlier sessions already settled, we need to
        # subtract already-settled amount. For simplicity, we sum all gifts for this
        # room and subtract what's already been settled in previous bills.
        already_settled = await self.db.scalar(
            select(func.coalesce(func.sum(SettlementBill.total_gift_fen), 0)).where(
                SettlementBill.room_id == room_id,
                SettlementBill.deleted_at.is_(None),
            )
        ) or 0

        session_gift_fen = total_gift_fen - already_settled

        if session_gift_fen <= 0:
            return None

        # Calculate commission split
        # Per spec: streamer_earn = floor(gift_total * 70 / 100)
        streamer_earn_fen = (session_gift_fen * (100 - PLATFORM_COMMISSION_PCT)) // 100
        platform_fee_fen = session_gift_fen - streamer_earn_fen

        wallet = await self._get_or_create_wallet(streamer_id)
        now = _now_ts()

        # Move from pending to available
        wallet.pending_fen -= session_gift_fen
        wallet.available_fen += streamer_earn_fen
        wallet.total_earned_fen += streamer_earn_fen
        wallet.updated_at = now

        bill = SettlementBill(
            room_id=room_id,
            streamer_id=streamer_id,
            session_id=session_id,
            total_gift_fen=session_gift_fen,
            platform_fee_fen=platform_fee_fen,
            streamer_earn_fen=streamer_earn_fen,
            settled_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(bill)
        await self.db.flush()

        return SettlementBillInfo(
            id=bill.id,
            room_id=bill.room_id,
            streamer_id=bill.streamer_id,
            session_id=bill.session_id,
            total_gift_fen=bill.total_gift_fen,
            platform_fee_fen=bill.platform_fee_fen,
            streamer_earn_fen=bill.streamer_earn_fen,
            settled_at=_ts_to_iso(bill.settled_at),
            created_at=_ts_to_iso(bill.created_at),
        )

    # ── Add gift amount to pending ──────────────────────────────────

    async def add_pending_gift(self, streamer_id: int, gift_fen: int) -> None:
        """Add gift revenue to streamer's pending balance.

        Called when a gift is sent to the streamer during a live session.
        """
        wallet = await self._get_or_create_wallet(streamer_id)
        wallet.pending_fen += gift_fen
        wallet.updated_at = _now_ts()
        await self.db.flush()

    # ── Platform revenue ────────────────────────────────────────────

    async def get_platform_revenue(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> PlatformRevenueResponse:
        """Get platform revenue stats grouped by day.

        If no date range provided, defaults to last 30 days.
        """
        conditions = [SettlementBill.deleted_at.is_(None)]

        start_ts, end_ts_start = _date_to_ts_range(start_date)
        end_ts, _ = _date_to_ts_range(end_date)

        if start_ts is None and end_ts is None:
            # Default: last 30 days
            now_ts = _now_ts()
            start_ts = now_ts - 30 * 24 * 3600
            end_ts = now_ts + 1  # +1 so bills settled exactly at now_ts are included

        if start_ts is not None:
            conditions.append(SettlementBill.settled_at >= start_ts)
        if end_ts is not None:
            conditions.append(SettlementBill.settled_at < end_ts)

        # Aggregate by day using settled_at
        # SQLite doesn't support date_trunc, so we'll group in Python
        query = (
            select(SettlementBill)
            .where(*conditions)
            .order_by(SettlementBill.settled_at.desc())
        )
        bills = (await self.db.execute(query)).scalars().all()

        # Group by date
        daily_map: dict[str, dict] = {}
        for b in bills:
            date_str = datetime.fromtimestamp(b.settled_at, tz=timezone.utc).strftime("%Y-%m-%d")
            if date_str not in daily_map:
                daily_map[date_str] = {
                    "total_gift_fen": 0,
                    "platform_revenue_fen": 0,
                    "settlement_count": 0,
                }
            daily_map[date_str]["total_gift_fen"] += b.total_gift_fen
            daily_map[date_str]["platform_revenue_fen"] += b.platform_fee_fen
            daily_map[date_str]["settlement_count"] += 1

        items = [
            DailyRevenueItem(
                date=date_str,
                total_gift_fen=d["total_gift_fen"],
                platform_revenue_fen=d["platform_revenue_fen"],
                settlement_count=d["settlement_count"],
            )
            for date_str, d in sorted(daily_map.items(), reverse=True)
        ]

        totals = await self.db.execute(
            select(
                func.coalesce(func.sum(SettlementBill.platform_fee_fen), 0),
                func.coalesce(func.sum(SettlementBill.total_gift_fen), 0),
                func.count(SettlementBill.id),
            ).where(*conditions)
        )
        total_platform, total_gift, total_count = totals.one()

        return PlatformRevenueResponse(
            items=items,
            total_platform_revenue_fen=total_platform,
            total_gift_fen=total_gift,
            total_settlements=total_count,
        )
