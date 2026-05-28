"""Interaction service — danmaku, like, gift business logic."""

import re
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AppException,
    ForbiddenError,
    NotFoundError,
    RoomBannedError,
    RoomNotFoundError,
    ValidationError,
)
from app.core.redis import get_redis
from app.models.interaction import (
    ALL_VALID_COLORS,
    DIAMOND_LEVEL_THRESHOLD,
    MAX_PIN_DURATION_SECONDS,
    Danmaku,
    ForbiddenWord,
    Gift,
    GiftRecord,
    get_allowed_colors,
)
from app.models.room import Room
from app.models.user import User, Wallet
from app.schemas.interaction import (
    DanmakuResponse,
    ForbiddenWordResponse,
    GiftRankItem,
    GiftResponse,
    LikeResponse,
    SendGiftResponse,
)


# ── Helpers ───────────────────────────────────────────────────────


def _now_ts() -> int:
    return int(time.time())


def _ts_to_iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _ts_to_iso_req(ts: int) -> str:
    """Convert a non-null timestamp to ISO 8601 string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ── Redis key patterns ────────────────────────────────────────────

DANMAKU_RATE_KEY = "danmaku:rate:{room_id}:{user_id}"
LIKE_COUNT_KEY = "room:{room_id}:likes:{user_id}"
LIKE_TOTAL_KEY = "room:{room_id}:total_likes"

# Danmaku rate limit: max 3 per 5 seconds
DANMAKU_RATE_LIMIT = 3
DANMAKU_RATE_WINDOW = 5  # seconds

# Like limit per user per session
MAX_LIKES_PER_USER = 1000


# ── Exception classes ─────────────────────────────────────────────


class InsufficientBalanceError(AppException):
    """Balance too low to send gift (4001)."""

    def __init__(self):
        super().__init__(code=4001, message="余额不足", status_code=400)


class GiftNotFoundError(AppException):
    """Gift not found (4003)."""

    def __init__(self):
        super().__init__(code=4003, message="礼物不存在", status_code=400)


class DanmakuRateLimitedError(AppException):
    """Danmaku rate limit hit."""

    def __init__(self):
        super().__init__(code=1001, message="发送频率过快，请稍后再试", status_code=429)


class ForbiddenContentError(AppException):
    """Danmaku contains forbidden word."""

    def __init__(self):
        super().__init__(code=1001, message="弹幕内容包含违禁词", status_code=400)


class LikeLimitExceededError(AppException):
    """Max likes per session reached."""

    def __init__(self):
        super().__init__(code=1001, message="本场直播点赞次数已达上限", status_code=400)


class RoomNotLiveError(AppException):
    """Room is not live for interaction."""

    def __init__(self):
        super().__init__(code=3002, message="直播间未在直播中", status_code=400)


# ── Service ───────────────────────────────────────────────────────


class InteractionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Room helpers ──────────────────────────────────────────────

    async def _get_live_room(self, room_id: int) -> Room:
        """Get a room that must exist, not deleted, and be live."""
        result = await self.db.execute(
            select(Room).where(Room.id == room_id, Room.deleted_at.is_(None))
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError()
        if room.status == "banned":
            raise RoomBannedError()
        if room.status != "live":
            raise RoomNotLiveError()
        return room

    # ── Danmaku ───────────────────────────────────────────────────

    async def _get_forbidden_words(self) -> list[str]:
        """Get all active forbidden words from DB."""
        result = await self.db.execute(
            select(ForbiddenWord.word).where(ForbiddenWord.deleted_at.is_(None))
        )
        return [row[0] for row in result.all()]

    async def _check_forbidden_content(self, content: str) -> None:
        """Raise ForbiddenContentError if content contains any forbidden word."""
        words = await self._get_forbidden_words()
        for word in words:
            if word in content:
                raise ForbiddenContentError()

    async def _check_danmaku_rate_limit(self, room_id: int, user_id: int) -> None:
        """Sliding window rate limit: max 3 danmaku per 5 seconds per user per room."""
        r = await get_redis()
        key = DANMAKU_RATE_KEY.format(room_id=room_id, user_id=user_id)
        now = _now_ts()
        window_start = now - DANMAKU_RATE_WINDOW

        # Use sorted set: add current timestamp, remove old ones, check count
        member = f"{now}:{uuid.uuid4()}"
        await r.zadd(key, {member: now})
        await r.zremrangebyscore(key, 0, window_start)
        count = await r.zcard(key)
        await r.expire(key, DANMAKU_RATE_WINDOW + 1)

        if count > DANMAKU_RATE_LIMIT:
            raise DanmakuRateLimitedError()

    def _validate_danmaku_color(self, user_level: int, color: str) -> str:
        """Validate color is allowed for user level. Returns normalized color."""
        allowed = get_allowed_colors(user_level)
        if color not in allowed:
            raise ValidationError(
                f"当前等级不支持该颜色，可选颜色: {', '.join(sorted(allowed))}"
            )
        return color

    def _validate_pin(self, user_level: int, is_pinned: bool, pin_duration: int | None) -> None:
        """Validate pin permission and duration."""
        if not is_pinned:
            return
        if user_level < DIAMOND_LEVEL_THRESHOLD:
            raise ValidationError("仅钻石及以上等级用户可以使用置顶功能")
        if pin_duration is not None and pin_duration > MAX_PIN_DURATION_SECONDS:
            raise ValidationError(f"置顶时长不能超过 {MAX_PIN_DURATION_SECONDS} 秒")

    async def send_danmaku(
        self,
        user: User,
        room_id: int,
        content: str,
        color: str,
        is_pinned: bool = False,
        pin_duration_seconds: int | None = None,
    ) -> DanmakuResponse:
        """Send a danmaku in a room.

        Rules:
        - Room must be live
        - User must not be banned
        - Content must not contain forbidden words
        - Color must be allowed for user level
        - Pin only for diamond+ users
        - Rate limit: max 3 per 5 seconds
        """
        # Check room status
        room = await self._get_live_room(room_id)

        # Check user not banned
        if user.is_banned:
            raise ForbiddenError()

        # Check rate limit
        await self._check_danmaku_rate_limit(room_id, user.id)

        # Check forbidden words
        await self._check_forbidden_content(content)

        # Validate color
        self._validate_danmaku_color(user.level, color)

        # Validate pin
        self._validate_pin(user.level, is_pinned, pin_duration_seconds)

        now = _now_ts()
        danmaku = Danmaku(
            room_id=room_id,
            user_id=user.id,
            content=content,
            color=color,
            is_pinned=is_pinned,
            pin_duration_seconds=pin_duration_seconds if is_pinned else None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(danmaku)
        await self.db.flush()
        await self.db.refresh(danmaku)

        return DanmakuResponse(
            id=danmaku.id,
            room_id=danmaku.room_id,
            user_id=danmaku.user_id,
            username=user.username,
            nickname=user.nickname,
            content=danmaku.content,
            color=danmaku.color,
            is_pinned=danmaku.is_pinned,
            pin_duration_seconds=danmaku.pin_duration_seconds,
            created_at=_ts_to_iso_req(danmaku.created_at),
        )

    async def get_danmaku_history(self, room_id: int) -> list[DanmakuResponse]:
        """Get recent 100 danmaku for a room."""
        query = (
            select(Danmaku)
            .where(Danmaku.room_id == room_id, Danmaku.deleted_at.is_(None))
            .order_by(Danmaku.created_at.desc())
            .limit(100)
        )
        result = await self.db.execute(query)
        danmaku_list = result.scalars().all()

        # Collect user IDs for batch lookup
        user_ids = list({d.user_id for d in danmaku_list})
        users_map: dict[int, User] = {}
        if user_ids:
            user_result = await self.db.execute(
                select(User).where(User.id.in_(user_ids))
            )
            for u in user_result.scalars().all():
                users_map[u.id] = u

        responses = []
        for d in danmaku_list:
            u = users_map.get(d.user_id)
            responses.append(
                DanmakuResponse(
                    id=d.id,
                    room_id=d.room_id,
                    user_id=d.user_id,
                    username=u.username if u else "",
                    nickname=u.nickname if u else "",
                    content=d.content,
                    color=d.color,
                    is_pinned=d.is_pinned,
                    pin_duration_seconds=d.pin_duration_seconds,
                    created_at=_ts_to_iso_req(d.created_at),
                )
            )

        return responses

    # ── Like ──────────────────────────────────────────────────────

    async def like_room(self, user: User, room_id: int) -> LikeResponse:
        """Like a room. Max 1000 likes per user per session.

        Returns the total number of likes the user has given in this session.
        """
        # Check room is live
        await self._get_live_room(room_id)

        r = await get_redis()
        like_key = LIKE_COUNT_KEY.format(room_id=room_id, user_id=user.id)
        total_key = LIKE_TOTAL_KEY.format(room_id=room_id)

        # Check limit
        current = await r.get(like_key)
        current_count = int(current) if current else 0

        if current_count >= MAX_LIKES_PER_USER:
            raise LikeLimitExceededError()

        # Increment user's like count and total likes
        new_count = await r.incrby(like_key, 1)
        await r.incrby(total_key, 1)

        # Set TTL on user key if this is the first like (24h default)
        if new_count == 1:
            await r.expire(like_key, 86400)

        return LikeResponse(
            room_id=room_id,
            user_id=user.id,
            total_likes=new_count,
        )

    async def get_like_count(self, room_id: int) -> int:
        """Get total like count for a room from Redis."""
        r = await get_redis()
        total_key = LIKE_TOTAL_KEY.format(room_id=room_id)
        val = await r.get(total_key)
        return int(val) if val else 0

    # ── Gifts ─────────────────────────────────────────────────────

    async def get_gift_list(self) -> list[GiftResponse]:
        """Return all active gifts."""
        result = await self.db.execute(
            select(Gift).where(
                Gift.deleted_at.is_(None),
                Gift.is_active.is_(True),
            )
        )
        gifts = result.scalars().all()
        return [
            GiftResponse(
                id=g.id,
                name=g.name,
                price_fen=g.price_fen,
                effect=g.effect,
                icon_url=g.icon_url,
                is_active=g.is_active,
            )
            for g in gifts
        ]

    async def send_gift(
        self,
        user: User,
        room_id: int,
        gift_id: int,
        quantity: int,
    ) -> SendGiftResponse:
        """Send a gift in a room.

        Rules:
        - Room must be live
        - Gift must exist and be active
        - User must have sufficient balance
        - Atomic: deduct balance, record transaction, increment streamer earnings

        Diamond-tier gifts (announcement, guardian) trigger room-wide announcements.
        """
        # Check room is live
        room = await self._get_live_room(room_id)

        # Get gift
        result = await self.db.execute(
            select(Gift).where(
                Gift.id == gift_id,
                Gift.deleted_at.is_(None),
                Gift.is_active.is_(True),
            )
        )
        gift = result.scalar_one_or_none()
        if gift is None:
            raise GiftNotFoundError()

        total_amount = gift.price_fen * quantity

        # Get sender's wallet with row lock (FOR UPDATE)
        wallet_result = await self.db.execute(
            select(Wallet)
            .where(Wallet.user_id == user.id, Wallet.deleted_at.is_(None))
            .with_for_update()
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet is None:
            raise InsufficientBalanceError()

        if wallet.balance_fen < total_amount:
            raise InsufficientBalanceError()

        # Deduct balance
        wallet.balance_fen -= total_amount
        wallet.updated_at = _now_ts()

        # Update user total consumption (for level calc)
        user_query = await self.db.execute(
            select(User).where(User.id == user.id).with_for_update()
        )
        sender = user_query.scalar_one()
        sender.total_consumed_fen += total_amount

        # Record gift transaction
        now = _now_ts()
        record = GiftRecord(
            room_id=room_id,
            sender_id=user.id,
            receiver_id=room.streamer_id,
            gift_id=gift.id,
            quantity=quantity,
            total_amount_fen=total_amount,
            gift_name=gift.name,
            gift_effect=gift.effect,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)

        # Determine if announcement needed
        is_announcement = gift.effect in ("announcement", "guardian")

        return SendGiftResponse(
            gift_record_id=record.id,
            gift_name=gift.name,
            quantity=quantity,
            total_amount_fen=total_amount,
            balance_after_fen=wallet.balance_fen,
            is_announcement=is_announcement,
        )

    async def get_gift_rank(self, room_id: int) -> list[GiftRankItem]:
        """Get top 10 gift senders by total amount for a room's current session.

        Only counts gifts sent while room is in current live session.
        """
        # Get room to find started_at
        result = await self.db.execute(
            select(Room).where(Room.id == room_id, Room.deleted_at.is_(None))
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError()

        # Sum gift amounts by sender in this room
        query = (
            select(
                GiftRecord.sender_id,
                func.sum(GiftRecord.total_amount_fen).label("total_amount"),
            )
            .where(
                GiftRecord.room_id == room_id,
                GiftRecord.deleted_at.is_(None),
            )
        )
        # If room has started_at, only count gifts after session start
        if room.started_at is not None:
            query = query.where(GiftRecord.created_at >= room.started_at)

        query = (
            query.group_by(GiftRecord.sender_id)
            .order_by(desc("total_amount"))
            .limit(10)
        )

        result = await self.db.execute(query)
        rows = result.all()

        if not rows:
            return []

        # Batch load user info
        sender_ids = [row[0] for row in rows]
        user_result = await self.db.execute(
            select(User).where(User.id.in_(sender_ids))
        )
        users_map: dict[int, User] = {u.id: u for u in user_result.scalars().all()}

        rank_items = []
        for rank, (sender_id, total_amount) in enumerate(rows, start=1):
            u = users_map.get(sender_id)
            rank_items.append(
                GiftRankItem(
                    user_id=sender_id,
                    username=u.username if u else "",
                    nickname=u.nickname if u else "",
                    avatar_url=u.avatar_url if u else None,
                    total_amount_fen=total_amount or 0,
                    rank=rank,
                )
            )

        return rank_items

    # ── Forbidden Words (admin) ───────────────────────────────────

    async def list_forbidden_words(self) -> list[ForbiddenWordResponse]:
        """Get all active forbidden words."""
        result = await self.db.execute(
            select(ForbiddenWord).where(ForbiddenWord.deleted_at.is_(None))
        )
        words = result.scalars().all()
        return [
            ForbiddenWordResponse(
                id=w.id,
                word=w.word,
                created_at=_ts_to_iso_req(w.created_at),
            )
            for w in words
        ]

    async def create_forbidden_word(self, word: str) -> ForbiddenWordResponse:
        """Add a forbidden word."""
        # Check duplicate
        existing = await self.db.execute(
            select(ForbiddenWord).where(
                ForbiddenWord.word == word,
                ForbiddenWord.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise ValidationError("该违禁词已存在")

        now = _now_ts()
        fw = ForbiddenWord(
            word=word,
            created_at=now,
            updated_at=now,
        )
        self.db.add(fw)
        await self.db.flush()
        await self.db.refresh(fw)

        return ForbiddenWordResponse(
            id=fw.id,
            word=fw.word,
            created_at=_ts_to_iso_req(fw.created_at),
        )

    async def delete_forbidden_word(self, word_id: int) -> None:
        """Soft-delete a forbidden word."""
        result = await self.db.execute(
            select(ForbiddenWord).where(
                ForbiddenWord.id == word_id,
                ForbiddenWord.deleted_at.is_(None),
            )
        )
        fw = result.scalar_one_or_none()
        if fw is None:
            raise NotFoundError("违禁词")

        fw.deleted_at = _now_ts()
        fw.updated_at = _now_ts()
        await self.db.flush()
