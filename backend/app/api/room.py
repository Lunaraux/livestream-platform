"""Room API routes — create, start, end, list, search, update, ban, unban.

IMPORTANT: Specific routes (recommended, search) MUST come before parameterized
routes (/{room_id}) in FastAPI to avoid route matching conflicts.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUserDep, require_role
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedData, PaginationParams
from app.schemas.room import (
    BanRoomRequest,
    CreateRoomRequest,
    RoomListItem,
    RoomResponse,
    RoomStats,
    UpdateRoomRequest,
)
from app.services.room_service import RoomService

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


# ── Create room ─────────────────────────────────────────────────────


@router.post("", response_model=ApiResponse[RoomResponse])
async def create_room(
    body: CreateRoomRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RoomResponse]:
    """Create a new livestream room.

    POST /api/rooms
    - Requires streamer role + verified identity
    - Each streamer can only have ONE room

    Error codes: 1003 (not streamer), 1001 (not verified / already has room)
    """
    svc = RoomService(db)
    room = await svc.create_room(
        user=current_user,
        title=body.title,
        description=body.description,
        category=body.category,
        cover_url=body.cover_url,
    )
    return ApiResponse(code=0, message="直播间创建成功", data=room)


# ── List rooms ──────────────────────────────────────────────────────


@router.get("", response_model=ApiResponse[PaginatedData[RoomListItem]])
async def list_rooms(
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
    category: str | None = Query(default=None, description="分类过滤"),
    sort_by: str = Query(default="viewers", description="排序方式: viewers | time"),
) -> ApiResponse[PaginatedData[RoomListItem]]:
    """List live rooms with filtering and sorting.

    GET /api/rooms
    - Only returns live rooms
    - Supports ?category=game, ?sort_by=viewers|time
    - Pagination: ?page=1&page_size=20
    """
    svc = RoomService(db)
    result = await svc.list_rooms(
        pagination=pagination,
        category=category,
        sort_by=sort_by,
    )
    return ApiResponse(code=0, message="success", data=result)


# ── Recommended rooms ───────────────────────────────────────────────


@router.get("/recommended", response_model=ApiResponse[list[RoomListItem]])
async def get_recommended(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[RoomListItem]]:
    """Return the top 10 recommended rooms by viewer count.

    GET /api/rooms/recommended
    - Returns up to 10 live rooms, sorted by current viewers descending
    - Accessible to all users
    """
    svc = RoomService(db)
    rooms = await svc.get_recommended_rooms()
    return ApiResponse(code=0, message="success", data=rooms)


# ── Search rooms ────────────────────────────────────────────────────


@router.get("/search", response_model=ApiResponse[PaginatedData[RoomListItem]])
async def search_rooms(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> ApiResponse[PaginatedData[RoomListItem]]:
    """Search live rooms by title.

    GET /api/rooms/search?q=关键词
    - Supports pagination: ?q=xxx&page=1&page_size=20
    """
    svc = RoomService(db)
    result = await svc.search_rooms(keyword=q, pagination=pagination)
    return ApiResponse(code=0, message="success", data=result)


# ── Get room detail ─────────────────────────────────────────────────


@router.get("/{room_id}", response_model=ApiResponse[RoomResponse])
async def get_room_detail(
    room_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RoomResponse]:
    """Get room detail including streamer info and current viewers.

    GET /api/rooms/{room_id}
    - Returns room info, streamer info, current viewers, status
    - Accessible to all users (guests included)

    Error codes: 3001 (not found)
    """
    svc = RoomService(db)
    room = await svc.get_room_detail(room_id)
    return ApiResponse(code=0, message="success", data=room)


# ── Start streaming ─────────────────────────────────────────────────


@router.post("/{room_id}/start", response_model=ApiResponse[RoomResponse])
async def start_stream(
    room_id: int,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RoomResponse]:
    """Start streaming in a room.

    POST /api/rooms/{room_id}/start
    - Only the room owner can start
    - Room must be in idle state

    Error codes: 3001 (not found), 1003 (not owner), 1001 (bad status)
    """
    svc = RoomService(db)
    room = await svc.start_stream(user=current_user, room_id=room_id)
    return ApiResponse(code=0, message="开播成功", data=room)


# ── End streaming ───────────────────────────────────────────────────


@router.post("/{room_id}/end", response_model=ApiResponse[RoomStats])
async def end_stream(
    room_id: int,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RoomStats]:
    """End streaming in a room.

    POST /api/rooms/{room_id}/end
    - Only the room owner can end
    - Records session duration, peak viewers, total sessions

    Error codes: 3001 (not found), 1003 (not owner), 1001 (not live)
    """
    svc = RoomService(db)
    stats = await svc.end_stream(user=current_user, room_id=room_id)
    return ApiResponse(code=0, message="直播已结束", data=stats)


# ── Update room ─────────────────────────────────────────────────────


@router.put("/{room_id}", response_model=ApiResponse[RoomResponse])
async def update_room(
    room_id: int,
    body: UpdateRoomRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RoomResponse]:
    """Update room info.

    PUT /api/rooms/{room_id}
    - Only the room owner can update
    - Only provided (non-None) fields are updated

    Error codes: 3001 (not found), 1003 (not owner)
    """
    svc = RoomService(db)
    room = await svc.update_room(
        user=current_user,
        room_id=room_id,
        title=body.title,
        description=body.description,
        category=body.category,
        cover_url=body.cover_url,
    )
    return ApiResponse(code=0, message="更新成功", data=room)


# ── Admin routes ────────────────────────────────────────────────────

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_router.post("/rooms/{room_id}/ban", response_model=ApiResponse[dict])
async def ban_room(
    room_id: int,
    body: BanRoomRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Admin: ban a room.

    POST /api/admin/rooms/{room_id}/ban
    - Requires admin role
    - Sets room status to banned

    Error codes: 3001 (not found), 1001 (already banned/ended), 1003 (not admin)
    """
    svc = RoomService(db)
    result = await svc.ban_room(admin=current_user, room_id=room_id, reason=body.reason)
    return ApiResponse(code=0, message="直播间已封禁", data=result)


@admin_router.post("/rooms/{room_id}/unban", response_model=ApiResponse[dict])
async def unban_room(
    room_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Admin: unban a room.

    POST /api/admin/rooms/{room_id}/unban
    - Requires admin role
    - Restores room status to idle

    Error codes: 3001 (not found), 1001 (not banned), 1003 (not admin)
    """
    svc = RoomService(db)
    result = await svc.unban_room(admin=current_user, room_id=room_id)
    return ApiResponse(code=0, message="直播间已解封", data=result)
