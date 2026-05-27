"""FastAPI dependency injection — DB session, current user, role checks."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AccountBannedError, AccountLockedError, ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token, is_token_blacklisted
from app.models.user import User

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> User:
    """Validate Bearer token and return the current user.

    Raises:
        UnauthorizedError: Missing/invalid token or token blacklisted.
        AccountLockedError: Account temporarily locked.
        AccountBannedError: Account banned.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError()

    token = authorization[7:]  # strip "Bearer "

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise UnauthorizedError()

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id:
        raise UnauthorizedError()

    # Check token blacklist
    if jti and await is_token_blacklisted(jti):
        raise UnauthorizedError()

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None or user.deleted_at is not None:
        raise UnauthorizedError()

    if user.is_banned:
        raise AccountBannedError()

    # Check temporary lock
    if user.locked_until and user.locked_until > int(time.time()):
        raise AccountLockedError()

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> User | None:
    """Try to get current user, return None if not authenticated (guest)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization, db)
    except (UnauthorizedError, AccountBannedError, AccountLockedError):
        return None


OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]


def require_role(*roles: str):
    """Factory: dependency that requires the current user to have one of the given roles."""

    async def _require_role(current_user: CurrentUserDep) -> User:
        if current_user.role not in roles:
            raise ForbiddenError()
        return current_user

    return _require_role
