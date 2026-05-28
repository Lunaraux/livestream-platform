"""Interaction API routes — danmaku, like, gift, gift-rank, forbidden-words."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUserDep, require_role
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.interaction import (
    DanmakuResponse,
    DanmakuSendRequest,
    ForbiddenWordCreateRequest,
    ForbiddenWordResponse,
    GiftRankItem,
    GiftResponse,
    LikeResponse,
    SendGiftRequest,
    SendGiftResponse,
)
from app.services.interaction_service import InteractionService

router = APIRouter(tags=["interaction"])


# ── Danmaku ───────────────────────────────────────────────────────


@router.post(
    "/api/rooms/{room_id}/danmaku",
    response_model=ApiResponse[DanmakuResponse],
)
async def send_danmaku(
    room_id: int,
    body: DanmakuSendRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[DanmakuResponse]:
    """Send a danmaku in a room.

    POST /api/rooms/{room_id}/danmaku
    - Requires login
    - Room must be live
    - Color allowed by user level
    - Content filtered for forbidden words
    - Rate limit: max 3 per 5 seconds

    Error codes: 1002 (not logged in), 3002 (not live), 1001 (rate limit/forbidden)
    """
    svc = InteractionService(db)
    data = await svc.send_danmaku(
        user=current_user,
        room_id=room_id,
        content=body.content,
        color=body.color,
        is_pinned=body.is_pinned,
        pin_duration_seconds=body.pin_duration_seconds,
    )
    return ApiResponse(code=0, message="发送成功", data=data)


@router.get(
    "/api/rooms/{room_id}/danmaku",
    response_model=ApiResponse[list[DanmakuResponse]],
)
async def get_danmaku_history(
    room_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[DanmakuResponse]]:
    """Get recent danmaku history for a room.

    GET /api/rooms/{room_id}/danmaku
    - Returns most recent 100 danmaku
    - Accessible to all users (including guests)
    """
    svc = InteractionService(db)
    data = await svc.get_danmaku_history(room_id)
    return ApiResponse(code=0, message="success", data=data)


# ── Like ──────────────────────────────────────────────────────────


@router.post(
    "/api/rooms/{room_id}/like",
    response_model=ApiResponse[LikeResponse],
)
async def like_room(
    room_id: int,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LikeResponse]:
    """Like a room.

    POST /api/rooms/{room_id}/like
    - Requires login
    - Room must be live
    - Max 1000 likes per user per session

    Error codes: 1002 (not logged in), 3002 (not live), 1001 (limit reached)
    """
    svc = InteractionService(db)
    data = await svc.like_room(user=current_user, room_id=room_id)
    return ApiResponse(code=0, message="点赞成功", data=data)


# ── Gifts ─────────────────────────────────────────────────────────


@router.get(
    "/api/gifts",
    response_model=ApiResponse[list[GiftResponse]],
)
async def get_gift_list(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[GiftResponse]]:
    """Get all available gifts.

    GET /api/gifts
    - Returns active gift catalog with prices and effects
    - Accessible to all users
    """
    svc = InteractionService(db)
    data = await svc.get_gift_list()
    return ApiResponse(code=0, message="success", data=data)


@router.post(
    "/api/rooms/{room_id}/gifts",
    response_model=ApiResponse[SendGiftResponse],
)
async def send_gift(
    room_id: int,
    body: SendGiftRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SendGiftResponse]:
    """Send a gift in a room.

    POST /api/rooms/{room_id}/gifts
    - Requires login
    - Room must be live
    - Deducts balance from sender
    - Records gift transaction

    Error codes: 1002 (not logged in), 3002 (not live), 4001 (insufficient balance), 4003 (gift not found)
    """
    svc = InteractionService(db)
    data = await svc.send_gift(
        user=current_user,
        room_id=room_id,
        gift_id=body.gift_id,
        quantity=body.quantity,
    )
    return ApiResponse(code=0, message="赠送成功", data=data)


@router.get(
    "/api/rooms/{room_id}/gift-rank",
    response_model=ApiResponse[list[GiftRankItem]],
)
async def get_gift_rank(
    room_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[GiftRankItem]]:
    """Get gift leaderboard for a room.

    GET /api/rooms/{room_id}/gift-rank
    - Returns top 10 senders by total gift value
    - Accessible to all users
    """
    svc = InteractionService(db)
    data = await svc.get_gift_rank(room_id)
    return ApiResponse(code=0, message="success", data=data)


# ── Forbidden Words (admin) ───────────────────────────────────────

admin_router = APIRouter(prefix="/api/admin", tags=["admin-interaction"])


@admin_router.get(
    "/forbidden-words",
    response_model=ApiResponse[list[ForbiddenWordResponse]],
)
async def list_forbidden_words(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ForbiddenWordResponse]]:
    """Admin: list all forbidden words.

    GET /api/admin/forbidden-words
    - Requires admin role
    """
    svc = InteractionService(db)
    data = await svc.list_forbidden_words()
    return ApiResponse(code=0, message="success", data=data)


@admin_router.post(
    "/forbidden-words",
    response_model=ApiResponse[ForbiddenWordResponse],
)
async def create_forbidden_word(
    body: ForbiddenWordCreateRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ForbiddenWordResponse]:
    """Admin: add a forbidden word.

    POST /api/admin/forbidden-words
    - Requires admin role

    Error codes: 1001 (duplicate word)
    """
    svc = InteractionService(db)
    data = await svc.create_forbidden_word(word=body.word)
    return ApiResponse(code=0, message="添加成功", data=data)


@admin_router.delete(
    "/forbidden-words/{word_id}",
    response_model=ApiResponse[dict],
)
async def delete_forbidden_word(
    word_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Admin: delete a forbidden word.

    DELETE /api/admin/forbidden-words/{word_id}
    - Requires admin role
    - Soft delete

    Error codes: 1004 (not found)
    """
    svc = InteractionService(db)
    await svc.delete_forbidden_word(word_id)
    return ApiResponse(code=0, message="删除成功", data={"id": word_id})
