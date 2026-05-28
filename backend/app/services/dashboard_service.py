"""Dashboard service — admin platform stats and streamer session analytics.

Per 08-dashboard.md:
  Admin: realtime overview, trend data, room ranking, user funnel.
  Streamer: live session stats, history comparison.

Data sources:
  DB: users, rooms, gift_records, recharge_orders, danmaku, settlement_bills
  Redis: room viewer counts, total likes
"""

from __future__ import annotations

import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.redis import get_redis
from app.models.interaction import Danmaku, GiftRecord
from app.models.room import Room
from app.models.settlement import SettlementBill
from app.models.user import User
from app.schemas.dashboard import (
    DailyTrendItem,
    FunnelResponse,
    HistoryResponse,
    HistorySessionItem,
    PlatformRealtimeResponse,
    RoomRankItem,
    RoomRankResponse,
    StreamerLiveResponse,
    TrendResponse,
)

# ── Redis key patterns (must match connection_manager.py / interaction_service.py) ──

ROOM_VIEWERS_KEY = "room:{room_id}:viewers"
LIKE_TOTAL_KEY = "room:{room_id}:total_likes"
DANMAKU_RATE_KEY_PREFIX = "danmaku:rate:"  # per-user rate limit, not aggregated

# ── Helpers ────────────────────────────────────────────────────────────────


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


def _period_days(period: str) -> int:
    """Convert period string to number of days (including today)."""
    mapping = {"7d": 7, "30d": 30, "90d": 90}
    if period not in mapping:
        raise ValidationError(message="period 仅支持 7d / 30d / 90d")
    return mapping[period]


# ── Chinese word segmentation (simple) ─────────────────────────────────────

# Common Chinese stop words to filter out
_STOP_WORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "们", "那", "些", "什么", "怎么", "哪", "吗", "啊", "呢", "吧",
    "呀", "哈", "哦", "嗯", "呵呵", "嘿嘿", "哈哈",
    "还", "但", "只", "被", "把", "让", "给", "从", "对", "与",
    "为", "以", "之", "及", "等", "或", "其", "可",
    "来", "去", "做", "能", "想", "知道", "觉得", "可以", "应该",
    "这个", "那个", "哪个", "这里", "那里", "这样", "那样",
    "就是", "真的", "不是", "还是", "已经", "可能", "所以",
    "如果", "虽然", "但是", "因为", "然后", "而且", "不过",
    "一个", "一下", "一点", "一些", "一种", "一次",
    "太", "真", "多", "少", "大", "小", "好", "坏",
}


def _extract_keywords(content: str, min_len: int = 2) -> list[str]:
    """Extract Chinese keywords from danmaku content.

    Simple approach: split on non-Chinese characters, filter stop words and short tokens.
    """
    # Keep only Chinese characters
    chinese_only = re.sub(r"[^\u4e00-\u9fff]+", " ", content).strip()
    if not chinese_only:
        return []

    # Split by spaces to get individual tokens
    # For Chinese, we use bigrams as basic segmentation
    tokens: list[str] = []
    chars = list(chinese_only)
    for i in range(len(chars)):
        # Unigram
        if len(chars[i]) >= min_len:
            tokens.append(chars[i])
        # Bigram
        if i + 1 < len(chars):
            bigram = chars[i] + chars[i + 1]
            if len(bigram) >= min_len:
                tokens.append(bigram)

    # Also try splitting by spaces (for already-segmented content)
    for token in chinese_only.split():
        if len(token) >= min_len:
            tokens.append(token)

    # Filter stop words
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= min_len]


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard Service
# ═══════════════════════════════════════════════════════════════════════════


class DashboardService:
    """Admin and streamer dashboard analytics."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Admin: Platform Realtime ──────────────────────────────────────────

    async def get_platform_realtime(self) -> PlatformRealtimeResponse:
        """Return live platform snapshot per 08-dashboard.md."""
        today_start, today_end = _today_range()

        # 1) Online users: sum all viewer counts from Redis across live rooms
        online_users = await self._sum_redis_viewers()

        # 2) Live rooms: count rooms with status='live'
        live_rooms = await self.db.scalar(
            select(func.count(Room.id)).where(
                Room.status == "live",
                Room.deleted_at.is_(None),
            )
        ) or 0

        # 3) New users today
        new_users_today = await self.db.scalar(
            select(func.count(User.id)).where(
                User.created_at >= today_start,
                User.created_at < today_end,
                User.deleted_at.is_(None),
            )
        ) or 0

        # 4) Today recharge total (paid orders)
        from app.models.currency import RechargeOrder
        today_recharge_fen = await self.db.scalar(
            select(func.coalesce(func.sum(RechargeOrder.total_fen), 0)).where(
                RechargeOrder.status == "paid",
                RechargeOrder.paid_at >= today_start,
                RechargeOrder.paid_at < today_end,
                RechargeOrder.deleted_at.is_(None),
            )
        ) or 0

        # 5) Today gift total
        today_gift_fen = await self.db.scalar(
            select(func.coalesce(func.sum(GiftRecord.total_amount_fen), 0)).where(
                GiftRecord.created_at >= today_start,
                GiftRecord.created_at < today_end,
                GiftRecord.deleted_at.is_(None),
            )
        ) or 0

        # 6) Danmaku rate: count in last 60 seconds
        one_min_ago = _now_ts() - 60
        danmaku_last_min = await self.db.scalar(
            select(func.count(Danmaku.id)).where(
                Danmaku.created_at >= one_min_ago,
                Danmaku.deleted_at.is_(None),
            )
        ) or 0

        return PlatformRealtimeResponse(
            online_users=online_users,
            live_rooms=live_rooms,
            new_users_today=new_users_today,
            today_recharge_fen=today_recharge_fen,
            today_gift_fen=today_gift_fen,
            danmaku_rate_per_min=danmaku_last_min,
        )

    async def _sum_redis_viewers(self) -> int:
        """Sum viewer counts from Redis for all live rooms."""
        r = await get_redis()
        # Get all live room IDs from DB
        result = await self.db.execute(
            select(Room.id).where(
                Room.status == "live",
                Room.deleted_at.is_(None),
            )
        )
        live_room_ids = [row[0] for row in result.all()]

        total = 0
        for room_id in live_room_ids:
            val = await r.get(ROOM_VIEWERS_KEY.format(room_id=room_id))
            if val:
                total += int(val)
        return total

    # ── Admin: Trend Data ─────────────────────────────────────────────────

    async def get_trend(self, period: str) -> TrendResponse:
        """Return daily trend data for the given period."""
        days = _period_days(period)

        # Date range: [today - days + 1, today]
        now = datetime.now(timezone.utc)
        today_start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_ts = int((today_start_dt + timedelta(days=1)).timestamp())
        start_dt = today_start_dt - timedelta(days=days - 1)
        start_ts = int(start_dt.timestamp())

        items: list[DailyTrendItem] = []

        for i in range(days):
            day_start = start_dt + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            day_start_ts = int(day_start.timestamp())
            day_end_ts = int(day_end.timestamp())
            date_str = day_start.strftime("%Y-%m-%d")

            # New users on this day
            new_users = await self.db.scalar(
                select(func.count(User.id)).where(
                    User.created_at >= day_start_ts,
                    User.created_at < day_end_ts,
                    User.deleted_at.is_(None),
                )
            ) or 0

            # Revenue: sum of settled bills (platform fee + streamer earnings = total gift value)
            revenue_fen = await self.db.scalar(
                select(func.coalesce(func.sum(SettlementBill.total_gift_fen), 0)).where(
                    SettlementBill.settled_at >= day_start_ts,
                    SettlementBill.settled_at < day_end_ts,
                    SettlementBill.deleted_at.is_(None),
                )
            ) or 0

            # Live sessions: count settlement bills (one per session)
            live_sessions = await self.db.scalar(
                select(func.count(SettlementBill.id)).where(
                    SettlementBill.settled_at >= day_start_ts,
                    SettlementBill.settled_at < day_end_ts,
                    SettlementBill.deleted_at.is_(None),
                )
            ) or 0

            items.append(DailyTrendItem(
                date=date_str,
                new_users=new_users,
                revenue_fen=revenue_fen,
                live_sessions=live_sessions,
            ))

        return TrendResponse(period=period, items=items)

    # ── Admin: Room Ranking ───────────────────────────────────────────────

    async def get_room_rank(self) -> RoomRankResponse:
        """Return TOP 10 live rooms by current viewer count."""
        r = await get_redis()

        # Get all live rooms
        result = await self.db.execute(
            select(Room).where(
                Room.status == "live",
                Room.deleted_at.is_(None),
            )
        )
        rooms = result.scalars().all()

        # Get viewer counts from Redis
        ranked: list[tuple[int, Room]] = []
        for room in rooms:
            val = await r.get(ROOM_VIEWERS_KEY.format(room_id=room.id))
            viewer_count = int(val) if val else 0
            ranked.append((viewer_count, room))

        # Sort by viewer count descending, take top 10
        ranked.sort(key=lambda x: x[0], reverse=True)
        top10 = ranked[:10]

        items = [
            RoomRankItem(
                room_id=room.id,
                title=room.title,
                streamer_name=room.streamer.nickname if room.streamer else "未知",
                category=room.category,
                viewer_count=count,
            )
            for count, room in top10
        ]

        return RoomRankResponse(items=items)

    # ── Admin: User Funnel ────────────────────────────────────────────────

    async def get_funnel(self) -> FunnelResponse:
        """Return user growth funnel: registered → consuming → active streamers."""
        # Registered users (non-deleted)
        registered = await self.db.scalar(
            select(func.count(User.id)).where(
                User.deleted_at.is_(None),
            )
        ) or 0

        # Consuming users (have spent coins)
        consuming = await self.db.scalar(
            select(func.count(User.id)).where(
                User.total_consumed_fen > 0,
                User.deleted_at.is_(None),
            )
        ) or 0

        # Active streamers (verified + have a non-deleted room)
        active_streamers = await self.db.scalar(
            select(func.count(func.distinct(User.id))).where(
                User.streamer_verified.is_(True),
                User.deleted_at.is_(None),
                User.id.in_(
                    select(Room.streamer_id).where(
                        Room.deleted_at.is_(None),
                    )
                ),
            )
        ) or 0

        return FunnelResponse(
            registered_users=registered,
            consuming_users=consuming,
            active_streamers=active_streamers,
        )

    # ── Streamer: Live Session Stats ──────────────────────────────────────

    async def get_streamer_live(self, streamer: User) -> StreamerLiveResponse:
        """Return current live session stats for the streamer's active room."""
        # Find the streamer's live room
        result = await self.db.execute(
            select(Room).where(
                Room.streamer_id == streamer.id,
                Room.status == "live",
                Room.deleted_at.is_(None),
            )
        )
        room = result.scalar_one_or_none()

        if room is None:
            # No live room — return zeros
            return StreamerLiveResponse()

        r = await get_redis()
        room_id = room.id

        # 1) Online viewers from Redis
        val = await r.get(ROOM_VIEWERS_KEY.format(room_id=room_id))
        online_viewers = int(val) if val else 0

        # 2) Cumulative viewers: peak_viewers on the room (best approximation)
        # In practice this would be tracked in Redis, but we use DB peak as fallback
        cumulative_viewers = room.peak_viewers

        # 3) Danmaku count for this room (all time, non-deleted)
        danmaku_count = await self.db.scalar(
            select(func.count(Danmaku.id)).where(
                Danmaku.room_id == room_id,
                Danmaku.deleted_at.is_(None),
            )
        ) or 0

        # 4) Like count from Redis
        like_val = await r.get(LIKE_TOTAL_KEY.format(room_id=room_id))
        like_count = int(like_val) if like_val else 0

        # 5) Gift revenue for this room
        gift_fen = await self.db.scalar(
            select(func.coalesce(func.sum(GiftRecord.total_amount_fen), 0)).where(
                GiftRecord.room_id == room_id,
                GiftRecord.deleted_at.is_(None),
            )
        ) or 0

        # 6) Word cloud: extract keywords from recent danmaku
        word_cloud = await self._build_word_cloud(room_id)

        return StreamerLiveResponse(
            online_viewers=online_viewers,
            cumulative_viewers=cumulative_viewers,
            danmaku_count=danmaku_count,
            like_count=like_count,
            gift_fen=gift_fen,
            word_cloud=word_cloud,
        )

    async def _build_word_cloud(self, room_id: int, top_n: int = 20) -> list[str]:
        """Build a word cloud from recent danmaku in the room.

        Returns TOP N keywords as strings (can be displayed as-is or rendered
        in a word cloud component on the frontend).
        """
        # Get recent danmaku (last 500 for performance)
        result = await self.db.execute(
            select(Danmaku.content)
            .where(
                Danmaku.room_id == room_id,
                Danmaku.deleted_at.is_(None),
            )
            .order_by(Danmaku.id.desc())
            .limit(500)
        )
        contents = [row[0] for row in result.all()]

        if not contents:
            return []

        # Extract keywords and count
        counter: Counter[str] = Counter()
        for content in contents:
            keywords = _extract_keywords(content)
            counter.update(keywords)

        # Return top N keywords (just the words, frontend handles rendering)
        return [word for word, _ in counter.most_common(top_n)]

    # ── Streamer: History Comparison ──────────────────────────────────────

    async def get_streamer_history(self, streamer: User) -> HistoryResponse:
        """Return last 10 live sessions for comparison.

        Uses settlement bills as the authoritative record of completed sessions.
        Each bill represents one session.
        """
        result = await self.db.execute(
            select(SettlementBill)
            .where(
                SettlementBill.streamer_id == streamer.id,
                SettlementBill.deleted_at.is_(None),
            )
            .order_by(SettlementBill.settled_at.desc())
            .limit(10)
        )
        bills = result.scalars().all()

        items: list[HistorySessionItem] = []
        for bill in bills:
            # Get room info
            room_result = await self.db.execute(
                select(Room).where(Room.id == bill.room_id)
            )
            room = room_result.scalar_one_or_none()

            # Calculate duration from room timing if available
            duration_minutes = 0
            if room and room.started_at and room.ended_at:
                duration_minutes = (room.ended_at - room.started_at) // 60

            items.append(HistorySessionItem(
                session_id=bill.session_id,
                room_id=bill.room_id,
                title=room.title if room else "",
                duration_minutes=duration_minutes,
                peak_viewers=room.peak_viewers if room else 0,
                revenue_fen=bill.total_gift_fen,
                started_at=_ts_to_iso(room.started_at) if room else None,
                ended_at=_ts_to_iso(room.ended_at) if room else None,
            ))

        return HistoryResponse(items=items)
