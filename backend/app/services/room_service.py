"""Room service — business logic for creating, managing, and querying livestream rooms."""

import time
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ForbiddenError,
    InvalidRoomStatusError,
    NotFoundError,
    RoomAlreadyExistsError,
    RoomBannedError,
    RoomClosedError,
    RoomNotFoundError,
    StreamerNotVerifiedError,
)
from app.core.redis import get_redis
from app.models.room import ROOM_CATEGORIES, Room
from app.models.user import User
from app.schemas.common import PaginatedData, PaginationParams
from app.schemas.room import (
    RoomListItem,
    RoomResponse,
    RoomStats,
    StreamerBrief,
)


def _now_ts() -> int:
    return int(time.time())


def _ts_to_iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ── Redis viewer count helpers ─────────────────────────────────────

ROOM_VIEWERS_KEY = "room:{room_id}:viewers"


async def _get_room_viewers(room_id: int) -> int:
    """Get current viewer count from Redis for a room."""
    r = await get_redis()
    val = await r.get(ROOM_VIEWERS_KEY.format(room_id=room_id))
    return int(val) if val else 0


async def _set_room_viewers(room_id: int, count: int) -> None:
    """Set viewer count in Redis for a room."""
    r = await get_redis()
    await r.set(ROOM_VIEWERS_KEY.format(room_id=room_id), str(count))


async def _incr_room_viewers(room_id: int, delta: int) -> int:
    """Increment/decrement viewer count in Redis. Returns new count."""
    r = await get_redis()
    return await r.incrby(ROOM_VIEWERS_KEY.format(room_id=room_id), delta)


async def _del_room_viewers(room_id: int) -> None:
    """Remove viewer count key from Redis."""
    r = await get_redis()
    await r.delete(ROOM_VIEWERS_KEY.format(room_id=room_id))


def _streamer_to_brief(user: User | None) -> StreamerBrief | None:
    if user is None:
        return None
    return StreamerBrief(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
    )


async def _room_to_response(room: Room) -> RoomResponse:
    """Convert a Room ORM object to a RoomResponse, including viewer count from Redis."""
    viewers = await _get_room_viewers(room.id)
    return RoomResponse(
        id=room.id,
        streamer_id=room.streamer_id,
        title=room.title,
        description=room.description,
        category=room.category,
        cover_url=room.cover_url,
        status=room.status,
        peak_viewers=room.peak_viewers,
        current_viewers=viewers,
        total_sessions=room.total_sessions,
        started_at=_ts_to_iso(room.started_at),
        ended_at=_ts_to_iso(room.ended_at),
        created_at=_ts_to_iso(room.created_at),
        updated_at=_ts_to_iso(room.updated_at),
        streamer=_streamer_to_brief(room.streamer),
    )


async def _room_to_list_item(room: Room) -> RoomListItem:
    """Convert to lightweight list item."""
    viewers = await _get_room_viewers(room.id)
    return RoomListItem(
        id=room.id,
        streamer_id=room.streamer_id,
        title=room.title,
        category=room.category,
        cover_url=room.cover_url,
        status=room.status,
        current_viewers=viewers,
        started_at=_ts_to_iso(room.started_at),
        streamer=_streamer_to_brief(room.streamer),
    )


class RoomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Create room ─────────────────────────────────────────────────

    async def create_room(
        self,
        user: User,
        title: str,
        description: str | None,
        category: str,
        cover_url: str | None,
    ) -> RoomResponse:
        """Create a new livestream room.

        Requirements:
        - User must have role=streamer and streamer_verified=True
        - Each streamer can only have ONE room

        Raises:
            ForbiddenError: not a streamer.
            StreamerNotVerifiedError: not verified.
            RoomAlreadyExistsError: already has a room.
        """
        if user.role != "streamer":
            raise ForbiddenError()

        if not user.streamer_verified:
            raise StreamerNotVerifiedError()

        # Check: one room per streamer
        existing = await self.db.scalar(
            select(Room.id).where(
                Room.streamer_id == user.id,
                Room.deleted_at.is_(None),
            ).limit(1)
        )
        if existing is not None:
            raise RoomAlreadyExistsError()

        now = _now_ts()
        room = Room(
            streamer_id=user.id,
            title=title,
            description=description,
            category=category,
            cover_url=cover_url,
            status="idle",
            created_at=now,
            updated_at=now,
        )
        self.db.add(room)
        await self.db.flush()
        await self.db.refresh(room)

        # Initialize viewer count in Redis
        await _set_room_viewers(room.id, 0)

        return await _room_to_response(room)

    # ── Start streaming ─────────────────────────────────────────────

    async def start_stream(self, user: User, room_id: int) -> RoomResponse:
        """Start streaming in a room.

        Only the room owner can start. Room must be in idle or banned state.
        Per spec: banned rooms can be started after admin unban — the state
        machine says banned→live (admin unban restores to idle first, then start).

        Raises:
            RoomNotFoundError: room not found.
            ForbiddenError: not the room owner.
            InvalidRoomStatusError: room not in startable state.
        """
        room = await self._get_room_or_404(room_id)

        if room.streamer_id != user.id:
            raise ForbiddenError()

        if room.status == "live":
            raise InvalidRoomStatusError("直播间已处于直播中状态")

        if room.status == "ended":
            raise RoomClosedError()

        if room.status == "banned":
            raise RoomBannedError()

        now = _now_ts()
        room.status = "live"
        room.started_at = now
        room.ended_at = None
        room.peak_viewers = 0
        room.updated_at = now

        # Reset viewer count in Redis
        await _set_room_viewers(room.id, 0)

        await self.db.flush()
        # Reload to get relationship data
        await self.db.refresh(room)

        # TODO: Push notification to followers via message queue (07-realtime)

        return await _room_to_response(room)

    # ── End streaming ───────────────────────────────────────────────

    async def end_stream(self, user: User, room_id: int) -> RoomStats:
        """End streaming in a room.

        Records session duration, peak viewers, increments total_sessions.
        The settlement flow is triggered by 06-settlement later.

        Raises:
            RoomNotFoundError: room not found.
            ForbiddenError: not the room owner.
            InvalidRoomStatusError: room is not live.
        """
        room = await self._get_room_or_404(room_id)

        if room.streamer_id != user.id:
            raise ForbiddenError()

        if room.status != "live":
            raise InvalidRoomStatusError("直播间未在直播中，无法结束")

        now = _now_ts()
        duration = now - (room.started_at or now)

        # Update peak viewers from Redis if Redis has higher count
        redis_viewers = await _get_room_viewers(room.id)
        peak = max(room.peak_viewers, redis_viewers)

        room.status = "ended"
        room.ended_at = now
        room.peak_viewers = peak
        room.total_sessions += 1
        room.updated_at = now

        # Clear Redis viewer count
        await _del_room_viewers(room.id)

        await self.db.flush()

        # TODO: Trigger settlement flow (06-settlement)

        return RoomStats(
            room_id=room.id,
            session_duration_seconds=duration,
            peak_viewers=peak,
            total_sessions=room.total_sessions,
        )

    # ── Get room detail ─────────────────────────────────────────────

    async def get_room_detail(self, room_id: int) -> RoomResponse:
        """Return room detail including streamer info and current viewers.

        Raises:
            RoomNotFoundError: room not found.
        """
        room = await self._get_room_or_404(room_id)
        return await _room_to_response(room)

    # ── List rooms ──────────────────────────────────────────────────

    async def list_rooms(
        self,
        pagination: PaginationParams,
        category: str | None = None,
        sort_by: str = "viewers",
    ) -> PaginatedData[RoomListItem]:
        """List live rooms with filtering and sorting.

        Per 03-room.md: only returns live rooms.
        Supports filter by category, sort by viewers (default) or started_at.

        Args:
            pagination: page/page_size.
            category: optional category filter.
            sort_by: "viewers" (sorted by Redis viewer count) or "time" (started_at desc).
        """
        offset = (pagination.page - 1) * pagination.page_size

        # Build base query: only non-deleted live rooms
        conditions = [
            Room.status == "live",
            Room.deleted_at.is_(None),
        ]

        if category is not None:
            conditions.append(Room.category == category)

        # Count
        total = await self.db.scalar(
            select(func.count(Room.id)).where(*conditions)
        )

        # Query
        query = select(Room).where(*conditions)

        if sort_by == "time":
            query = query.order_by(Room.started_at.desc())
        else:
            # Default: sort by started_at desc (viewer sorting done in-memory via Redis)
            query = query.order_by(Room.started_at.desc())

        query = query.offset(offset).limit(pagination.page_size)
        result = await self.db.execute(query)
        rooms = result.scalars().all()

        # Build items
        items = []
        for room in rooms:
            items.append(await _room_to_list_item(room))

        # If sort_by is "viewers", sort in-memory by current_viewers descending
        if sort_by == "viewers":
            items.sort(key=lambda r: r.current_viewers, reverse=True)

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    # ── Recommended rooms ───────────────────────────────────────────

    async def get_recommended_rooms(self) -> list[RoomListItem]:
        """Return top 10 rooms by current viewer count.

        Per 03-room.md: returns online人数最多的10个直播间.
        """
        query = (
            select(Room)
            .where(Room.status == "live", Room.deleted_at.is_(None))
            .order_by(Room.started_at.desc())
            .limit(50)  # Fetch more than 10 to allow in-memory sorting by viewers
        )
        result = await self.db.execute(query)
        rooms = result.scalars().all()

        items = [await _room_to_list_item(r) for r in rooms]
        items.sort(key=lambda r: r.current_viewers, reverse=True)
        return items[:10]

    # ── Search rooms ────────────────────────────────────────────────

    async def search_rooms(
        self, keyword: str, pagination: PaginationParams
    ) -> PaginatedData[RoomListItem]:
        """Search rooms by title (LIKE match).

        Per 03-room.md: searches by title only. Returns live rooms.
        """
        offset = (pagination.page - 1) * pagination.page_size
        pattern = f"%{keyword}%"

        conditions = [
            Room.status == "live",
            Room.deleted_at.is_(None),
            Room.title.ilike(pattern),
        ]

        total = await self.db.scalar(
            select(func.count(Room.id)).where(*conditions)
        )

        query = (
            select(Room)
            .where(*conditions)
            .order_by(Room.started_at.desc())
            .offset(offset)
            .limit(pagination.page_size)
        )
        result = await self.db.execute(query)
        rooms = result.scalars().all()

        items = [await _room_to_list_item(r) for r in rooms]

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    # ── Update room ─────────────────────────────────────────────────

    async def update_room(
        self,
        user: User,
        room_id: int,
        title: str | None,
        description: str | None,
        category: str | None,
        cover_url: str | None,
    ) -> RoomResponse:
        """Update room info. Only the room owner can update.

        Raises:
            RoomNotFoundError: room not found.
            ForbiddenError: not the room owner.
        """
        room = await self._get_room_or_404(room_id)

        if room.streamer_id != user.id:
            raise ForbiddenError()

        if title is not None:
            room.title = title
        if description is not None:
            room.description = description
        if category is not None:
            room.category = category
        if cover_url is not None:
            room.cover_url = cover_url

        room.updated_at = _now_ts()
        await self.db.flush()
        await self.db.refresh(room)

        return await _room_to_response(room)

    # ── Admin: ban room ─────────────────────────────────────────────

    async def ban_room(self, admin: User, room_id: int, reason: str) -> dict:
        """Admin bans a room.

        Per state machine: live → banned.
        A room can also be banned from idle state.

        Raises:
            RoomNotFoundError: room not found.
            InvalidRoomStatusError: room already ended or banned.
        """
        room = await self._get_room_or_404(room_id)

        if room.status == "banned":
            raise InvalidRoomStatusError("直播间已被封禁")

        if room.status == "ended":
            raise InvalidRoomStatusError("直播间已结束，无法封禁")

        now = _now_ts()

        # If it was live, record ended_at
        was_live = room.status == "live"
        if was_live:
            room.ended_at = now
            redis_viewers = await _get_room_viewers(room.id)
            room.peak_viewers = max(room.peak_viewers, redis_viewers)
            await _del_room_viewers(room.id)

        room.status = "banned"
        room.updated_at = now
        await self.db.flush()

        return {
            "room_id": room.id,
            "status": "banned",
            "reason": reason,
            "banned_by": admin.id,
            "was_live": was_live,
        }

    # ── Admin: unban room ───────────────────────────────────────────

    async def unban_room(self, admin: User, room_id: int) -> dict:
        """Admin unbans a room.

        Per state machine: banned → idle (admin can restore).

        Raises:
            RoomNotFoundError: room not found.
            InvalidRoomStatusError: room not in banned state.
        """
        room = await self._get_room_or_404(room_id)

        if room.status != "banned":
            raise InvalidRoomStatusError("直播间未被封禁，无需解封")

        now = _now_ts()
        room.status = "idle"
        room.updated_at = now
        await self.db.flush()

        return {
            "room_id": room.id,
            "status": "idle",
            "unbanned_by": admin.id,
        }

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_room_or_404(self, room_id: int) -> Room:
        """Fetch a room by ID or raise RoomNotFoundError."""
        result = await self.db.execute(
            select(Room).where(Room.id == room_id, Room.deleted_at.is_(None))
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError()
        return room
