"""User service — business logic for profiles, follow, password, ban, streamer verify."""

import time
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AlreadyFollowingError,
    ApplicationAlreadyExistsError,
    ApplicationNotFoundError,
    CannotFollowSelfError,
    ForbiddenError,
    NotFollowingError,
    NotFoundError,
    NotStreamerError,
    SamePasswordError,
    StreamerAlreadyVerifiedError,
    WrongPasswordError,
)
from app.core.security import hash_password, verify_password
from app.models.user import Follow, StreamerApplication, User
from app.schemas.auth import UserInfo
from app.schemas.common import PaginatedData, PaginationParams
from app.schemas.user import (
    LEVEL_NAMES,
    LEVEL_THRESHOLDS,
    FollowerItem,
    FollowStatus,
    FollowingItem,
    StreamerApplicationInfo,
    UserPublicProfile,
)


def _now_ts() -> int:
    return int(time.time())


def _ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _user_to_info(user: User) -> UserInfo:
    """Convert a User ORM object to a UserInfo response schema."""
    return UserInfo(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        bio=user.bio,
        role=user.role,
        level=user.level,
        streamer_verified=user.streamer_verified,
        created_at=_ts_to_iso(user.created_at),
        updated_at=_ts_to_iso(user.updated_at),
    )


def _mask_id_number(id_number: str) -> str:
    """Mask an ID number: keep first 3 and last 4 digits, mask the rest."""
    if len(id_number) <= 7:
        return id_number[0] + "*" * (len(id_number) - 2) + id_number[-1]
    return id_number[:3] + "*" * (len(id_number) - 7) + id_number[-4:]


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Get user profile ───────────────────────────────────────────

    async def get_user_profile(
        self, user_id: int, current_user: User | None = None
    ) -> UserPublicProfile:
        """Return a user's public profile.

        If current_user is provided, include is_following status.
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError("用户")

        # Count followers
        follower_count = await self.db.scalar(
            select(func.count(Follow.id)).where(
                Follow.followed_id == user_id, Follow.deleted_at.is_(None)
            )
        )

        # Count following
        following_count = await self.db.scalar(
            select(func.count(Follow.id)).where(
                Follow.follower_id == user_id, Follow.deleted_at.is_(None)
            )
        )

        # Check if current user follows this user
        is_following = False
        if current_user and current_user.id != user_id:
            exists = await self.db.scalar(
                select(Follow.id).where(
                    Follow.follower_id == current_user.id,
                    Follow.followed_id == user_id,
                    Follow.deleted_at.is_(None),
                ).limit(1)
            )
            is_following = exists is not None

        # Determine level name
        level_name = LEVEL_NAMES.get(user.level, "普通观众")

        return UserPublicProfile(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            avatar_url=user.avatar_url,
            role=user.role,
            level=user.level,
            streamer_verified=user.streamer_verified,
            created_at=_ts_to_iso(user.created_at),
            updated_at=_ts_to_iso(user.updated_at),
            bio=user.bio,
            follower_count=follower_count or 0,
            following_count=following_count or 0,
            is_following=is_following,
            level_name=level_name,
        )

    # ── Update profile ─────────────────────────────────────────────

    async def update_profile(
        self, user: User, nickname: str | None, avatar_url: str | None, bio: str | None
    ) -> UserInfo:
        """Update the current user's profile fields.

        Only updates fields that are explicitly provided (not None).
        """
        if nickname is not None:
            user.nickname = nickname
        if avatar_url is not None:
            user.avatar_url = avatar_url
        if bio is not None:
            user.bio = bio

        user.updated_at = _now_ts()
        await self.db.flush()
        return _user_to_info(user)

    # ── Change password ────────────────────────────────────────────

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        """Change the current user's password."""
        if not verify_password(old_password, user.password_hash):
            raise WrongPasswordError()

        if old_password == new_password:
            raise SamePasswordError()

        user.password_hash = hash_password(new_password)
        user.updated_at = _now_ts()
        await self.db.flush()

    # ── Follow / Unfollow ──────────────────────────────────────────

    async def follow_streamer(self, user: User, streamer_id: int) -> FollowStatus:
        """Follow a streamer.

        Raises:
            CannotFollowSelfError: trying to follow self.
            NotStreamerError: target is not a streamer.
            NotFoundError: streamer not found.
            AlreadyFollowingError: already following.
        """
        if user.id == streamer_id:
            raise CannotFollowSelfError()

        # Get target user
        result = await self.db.execute(
            select(User).where(User.id == streamer_id, User.deleted_at.is_(None))
        )
        target = result.scalar_one_or_none()
        if target is None:
            raise NotFoundError("用户")

        if target.role != "streamer":
            raise NotStreamerError()

        # Check if already following
        existing = await self.db.scalar(
            select(Follow).where(
                Follow.follower_id == user.id,
                Follow.followed_id == streamer_id,
                Follow.deleted_at.is_(None),
            ).limit(1)
        )
        if existing is not None:
            raise AlreadyFollowingError()

        now = _now_ts()
        follow = Follow(
            follower_id=user.id,
            followed_id=streamer_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(follow)
        await self.db.flush()

        return FollowStatus(is_following=True, message="关注成功")

    async def unfollow_streamer(self, user: User, streamer_id: int) -> FollowStatus:
        """Unfollow a streamer.

        Raises:
            NotFollowingError: not following this streamer.
        """
        result = await self.db.execute(
            select(Follow).where(
                Follow.follower_id == user.id,
                Follow.followed_id == streamer_id,
                Follow.deleted_at.is_(None),
            )
        )
        follow = result.scalar_one_or_none()
        if follow is None:
            raise NotFollowingError()

        # Soft delete
        follow.deleted_at = _now_ts()
        follow.updated_at = _now_ts()
        await self.db.flush()

        return FollowStatus(is_following=False, message="已取消关注")

    # ── Following / Followers lists ────────────────────────────────

    async def get_following(
        self, user: User, pagination: PaginationParams
    ) -> PaginatedData[FollowingItem]:
        """Return the list of streamers the current user follows."""
        offset = (pagination.page - 1) * pagination.page_size

        # Count
        total = await self.db.scalar(
            select(func.count(Follow.id)).where(
                Follow.follower_id == user.id,
                Follow.deleted_at.is_(None),
            )
        )

        # Query follows with joined followed user
        follow_query = (
            select(Follow)
            .where(Follow.follower_id == user.id, Follow.deleted_at.is_(None))
            .options(selectinload(Follow.followed))
            .offset(offset)
            .limit(pagination.page_size)
            .order_by(Follow.id.desc())
        )
        follows = (await self.db.execute(follow_query)).scalars().all()

        items: list[FollowingItem] = []
        for f in follows:
            streamer = f.followed
            items.append(
                FollowingItem(
                    id=streamer.id,
                    username=streamer.username,
                    nickname=streamer.nickname,
                    avatar_url=streamer.avatar_url,
                    bio=streamer.bio,
                    is_live=False,  # Will be determined by room service later
                )
            )

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_followers(
        self, user: User, pagination: PaginationParams
    ) -> PaginatedData[FollowerItem]:
        """Return the list of the current streamer's followers.

        Only streamers can view their followers.
        """
        if user.role != "streamer":
            raise ForbiddenError()

        offset = (pagination.page - 1) * pagination.page_size

        # Count
        total = await self.db.scalar(
            select(func.count(Follow.id)).where(
                Follow.followed_id == user.id,
                Follow.deleted_at.is_(None),
            )
        )

        # Query follows with joined follower user
        follow_query = (
            select(Follow)
            .where(Follow.followed_id == user.id, Follow.deleted_at.is_(None))
            .options(selectinload(Follow.follower))
            .offset(offset)
            .limit(pagination.page_size)
            .order_by(Follow.id.desc())
        )
        follows = (await self.db.execute(follow_query)).scalars().all()

        items: list[FollowerItem] = []
        for f in follows:
            follower = f.follower
            items.append(
                FollowerItem(
                    id=follower.id,
                    username=follower.username,
                    nickname=follower.nickname,
                    avatar_url=follower.avatar_url,
                )
            )

        return PaginatedData(
            items=items,
            total=total or 0,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    # ── Ban / Unban (admin) ────────────────────────────────────────

    async def ban_user(
        self, admin: User, target_id: int, reason: str, duration_hours: int
    ) -> dict:
        """Admin bans a user.

        Raises:
            NotFoundError: user not found.
            ForbiddenError: cannot ban another admin.
        """
        result = await self.db.execute(
            select(User).where(User.id == target_id, User.deleted_at.is_(None))
        )
        target = result.scalar_one_or_none()
        if target is None:
            raise NotFoundError("用户")

        if target.role == "admin":
            raise ForbiddenError()

        now = _now_ts()
        target.is_banned = True
        target.ban_reason = reason
        target.ban_until = now + duration_hours * 3600 if duration_hours > 0 else None
        target.updated_at = now
        await self.db.flush()

        return {
            "user_id": target.id,
            "is_banned": True,
            "ban_reason": reason,
            "banned_by": admin.id,
        }

    async def unban_user(self, admin: User, target_id: int) -> dict:
        """Admin unbans a user.

        Raises:
            NotFoundError: user not found.
        """
        result = await self.db.execute(
            select(User).where(User.id == target_id, User.deleted_at.is_(None))
        )
        target = result.scalar_one_or_none()
        if target is None:
            raise NotFoundError("用户")

        now = _now_ts()
        target.is_banned = False
        target.ban_until = None
        target.ban_reason = None
        target.updated_at = now
        await self.db.flush()

        return {
            "user_id": target.id,
            "is_banned": False,
            "unbanned_by": admin.id,
        }

    # ── Streamer application ───────────────────────────────────────

    async def apply_streamer(
        self, user: User, real_name: str, id_number: str
    ) -> StreamerApplicationInfo:
        """Submit a streamer verification application.

        Raises:
            StreamerAlreadyVerifiedError: already verified.
            ApplicationAlreadyExistsError: already submitted.
        """
        if user.streamer_verified:
            raise StreamerAlreadyVerifiedError()

        if user.role != "streamer":
            raise NotStreamerError()

        # Check if already has a pending application
        existing = await self.db.scalar(
            select(StreamerApplication).where(
                StreamerApplication.user_id == user.id,
                StreamerApplication.deleted_at.is_(None),
            ).limit(1)
        )
        if existing is not None:
            raise ApplicationAlreadyExistsError()

        masked_id = _mask_id_number(id_number)
        now = _now_ts()
        app = StreamerApplication(
            user_id=user.id,
            real_name=real_name,
            id_number=masked_id,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self.db.add(app)
        await self.db.flush()

        return StreamerApplicationInfo(
            id=app.id,
            user_id=app.user_id,
            real_name=app.real_name,
            id_number=app.id_number,
            status=app.status,
            reject_reason=app.reject_reason,
            created_at=_ts_to_iso(app.created_at),
            updated_at=_ts_to_iso(app.updated_at),
        )

    async def verify_streamer(
        self, admin: User, user_id: int, approved: bool, reject_reason: str | None
    ) -> dict:
        """Admin approves or rejects a streamer verification.

        Raises:
            ApplicationNotFoundError: no application found.
        """
        result = await self.db.execute(
            select(StreamerApplication)
            .where(
                StreamerApplication.user_id == user_id,
                StreamerApplication.status == "pending",
                StreamerApplication.deleted_at.is_(None),
            )
            .options(selectinload(StreamerApplication.user))
        )
        app = result.scalar_one_or_none()
        if app is None:
            raise ApplicationNotFoundError()

        now = _now_ts()
        app.status = "approved" if approved else "rejected"
        app.reviewed_by = admin.id
        if not approved:
            app.reject_reason = reject_reason
        app.updated_at = now

        if approved:
            app.user.streamer_verified = True
            app.user.updated_at = now

        await self.db.flush()

        return {
            "application_id": app.id,
            "user_id": app.user_id,
            "status": app.status,
            "reviewed_by": admin.id,
        }
