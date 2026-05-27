"""User API routes — profile, follow, password, ban, streamer verify."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUserDep, OptionalUserDep, get_current_user, require_role
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedData, PaginationParams
from app.schemas.user import (
    ApplyStreamerRequest,
    BanUserRequest,
    ChangePasswordRequest,
    FollowerItem,
    FollowingItem,
    StreamerApplicationInfo,
    UpdateProfileRequest,
    UserPublicProfile,
    VerifyStreamerRequest,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


# ── Public profile ─────────────────────────────────────────────────


@router.get("/{user_id}", response_model=ApiResponse[UserPublicProfile])
async def get_user_profile(
    user_id: int,
    current_user: OptionalUserDep = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserPublicProfile]:
    """Get a user's public profile.

    GET /api/users/{user_id}
    - Returns public info: nickname, level, follower count, etc.
    - If viewer is authenticated, includes is_following status.
    """
    svc = UserService(db)
    profile = await svc.get_user_profile(user_id, current_user=current_user)
    return ApiResponse(code=0, message="success", data=profile)


# ── Update profile ─────────────────────────────────────────────────


@router.put("/me", response_model=ApiResponse[dict])
async def update_profile(
    body: UpdateProfileRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Update personal profile.

    PUT /api/users/me
    - Editable fields: nickname, avatar_url, bio
    - Only provided (non-None) fields are updated
    """
    svc = UserService(db)
    user_info = await svc.update_profile(
        user=current_user,
        nickname=body.nickname,
        avatar_url=body.avatar_url,
        bio=body.bio,
    )
    return ApiResponse(code=0, message="更新成功", data=user_info.model_dump())


# ── Change password ────────────────────────────────────────────────


@router.post("/me/password", response_model=ApiResponse[None])
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """Change password.

    POST /api/users/me/password
    - Requires old password verification
    - New password must be 8-20 chars, include letter + digit
    """
    svc = UserService(db)
    await svc.change_password(
        user=current_user,
        old_password=body.old_password,
        new_password=body.new_password,
    )
    return ApiResponse(code=0, message="密码修改成功", data=None)


# ── Follow / Unfollow ──────────────────────────────────────────────


@router.post("/{streamer_id}/follow", response_model=ApiResponse[dict])
async def follow_streamer(
    streamer_id: int,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Follow a streamer.

    POST /api/users/{streamer_id}/follow
    """
    svc = UserService(db)
    result = await svc.follow_streamer(current_user, streamer_id)
    return ApiResponse(code=0, message=result.message, data=result.model_dump())


@router.delete("/{streamer_id}/follow", response_model=ApiResponse[dict])
async def unfollow_streamer(
    streamer_id: int,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Unfollow a streamer.

    DELETE /api/users/{streamer_id}/follow
    """
    svc = UserService(db)
    result = await svc.unfollow_streamer(current_user, streamer_id)
    return ApiResponse(code=0, message=result.message, data=result.model_dump())


# ── Following / Followers lists ────────────────────────────────────


@router.get("/me/following", response_model=ApiResponse[PaginatedData[FollowingItem]])
async def get_following(
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> ApiResponse[PaginatedData[FollowingItem]]:
    """Get the list of streamers I'm following.

    GET /api/users/me/following
    - Supports pagination: ?page=1&page_size=20
    """
    svc = UserService(db)
    result = await svc.get_following(current_user, pagination)
    return ApiResponse(code=0, message="success", data=result)


@router.get("/me/followers", response_model=ApiResponse[PaginatedData[FollowerItem]])
async def get_followers(
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> ApiResponse[PaginatedData[FollowerItem]]:
    """Get my followers list (streamers only).

    GET /api/users/me/followers
    - Supports pagination: ?page=1&page_size=20
    - Only streamers can view their followers
    """
    svc = UserService(db)
    result = await svc.get_followers(current_user, pagination)
    return ApiResponse(code=0, message="success", data=result)


# ── Apply for streamer ─────────────────────────────────────────────


@router.post("/me/apply-streamer", response_model=ApiResponse[dict])
async def apply_streamer(
    body: ApplyStreamerRequest,
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Apply for streamer verification.

    POST /api/users/me/apply-streamer
    - Requires role=streamer
    - ID number is masked before storage
    """
    svc = UserService(db)
    result = await svc.apply_streamer(
        user=current_user,
        real_name=body.real_name,
        id_number=body.id_number,
    )
    return ApiResponse(code=0, message="申请已提交，等待审核", data=result.model_dump())


# ── Admin routes ───────────────────────────────────────────────────

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_router.post("/users/{user_id}/ban", response_model=ApiResponse[dict])
async def ban_user(
    user_id: int,
    body: BanUserRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Admin: ban a user.

    POST /api/admin/users/{user_id}/ban
    - Requires admin role
    - duration_hours=0 means permanent ban
    """
    svc = UserService(db)
    result = await svc.ban_user(
        admin=current_user,
        target_id=user_id,
        reason=body.reason,
        duration_hours=body.duration_hours,
    )
    return ApiResponse(code=0, message="封禁成功", data=result)


@admin_router.post("/users/{user_id}/unban", response_model=ApiResponse[dict])
async def unban_user(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Admin: unban a user.

    POST /api/admin/users/{user_id}/unban
    - Requires admin role
    """
    svc = UserService(db)
    result = await svc.unban_user(admin=current_user, target_id=user_id)
    return ApiResponse(code=0, message="已解封", data=result)


@admin_router.post("/streamers/{user_id}/verify", response_model=ApiResponse[dict])
async def verify_streamer(
    user_id: int,
    body: VerifyStreamerRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Admin: approve or reject a streamer verification.

    POST /api/admin/streamers/{user_id}/verify
    - Requires admin role
    - approved=true → streamer_verified=true
    - approved=false → rejected with reason
    """
    svc = UserService(db)
    result = await svc.verify_streamer(
        admin=current_user,
        user_id=user_id,
        approved=body.approved,
        reject_reason=body.reject_reason,
    )
    msg = "审核通过" if body.approved else "审核已拒绝"
    return ApiResponse(code=0, message=msg, data=result)
