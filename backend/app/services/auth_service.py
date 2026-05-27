"""Auth service — business logic for registration, login, token refresh, logout."""

import time
import uuid
from datetime import datetime, timezone

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    UnauthorizedError,
    UsernameAlreadyExistsError,
)
from app.core.security import (
    blacklist_refresh_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_token_blacklisted,
    verify_password,
)
from app.models.user import User, Wallet
from app.schemas.auth import LoginResponse, UserInfo


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


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Register ───────────────────────────────────────────────────

    async def register(
        self, username: str, password: str, nickname: str, role: str
    ) -> UserInfo:
        """Register a new user and create their wallet.

        Raises:
            UsernameAlreadyExistsError (2001): username is taken.
        """
        # Check uniqueness
        result = await self.db.execute(
            select(User).where(User.username == username).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise UsernameAlreadyExistsError()

        # Hash password (bcrypt)
        password_hash = hash_password(password)

        # Create user
        now = _now_ts()
        user = User(
            username=username,
            password_hash=password_hash,
            nickname=nickname,
            role=role,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        await self.db.flush()  # Get user.id

        # Create wallet with 0 balance (per 01-auth.md)
        wallet = Wallet(
            user_id=user.id,
            balance_fen=0,
            created_at=now,
            updated_at=now,
        )
        self.db.add(wallet)

        return _user_to_info(user)

    # ── Login ──────────────────────────────────────────────────────

    async def login(
        self, username: str, password: str, ip_address: str | None = None
    ) -> LoginResponse:
        """Authenticate a user and return tokens.

        Raises:
            InvalidCredentialsError (2002): wrong username or password.
            AccountLockedError (2003): account locked after repeated failures.
        """
        result = await self.db.execute(
            select(User).where(User.username == username).limit(1)
        )
        user = result.scalar_one_or_none()

        if user is None or user.deleted_at is not None:
            raise InvalidCredentialsError()

        now = _now_ts()

        # Check if temporarily locked
        if user.locked_until and user.locked_until > now:
            raise AccountLockedError()

        # Verify password
        if not verify_password(password, user.password_hash):
            # Increment failure count
            user.login_failed_count += 1
            if user.login_failed_count >= settings.MAX_LOGIN_FAILURES:
                user.locked_until = now + settings.ACCOUNT_LOCK_MINUTES * 60
            user.updated_at = now
            # Explicitly commit failure count so it persists despite get_db's rollback on exception
            await self.db.commit()
            raise InvalidCredentialsError()

        # Success: reset failure count, record login
        user.login_failed_count = 0
        user.locked_until = None
        user.last_login_at = now
        user.last_login_ip = ip_address
        user.updated_at = now

        # Create tokens
        token_jti = str(uuid.uuid4())
        access_token, access_exp = create_access_token(
            {"sub": str(user.id), "jti": token_jti}
        )
        refresh_token, refresh_exp = create_refresh_token(
            {"sub": str(user.id), "jti": str(uuid.uuid4()), "type": "refresh"}
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user_info=_user_to_info(user),
        )

    # ── Refresh ────────────────────────────────────────────────────

    async def refresh(self, refresh_token_str: str) -> dict:
        """Validate a refresh token and issue a new access token.

        Returns: {"access_token": str}

        Raises:
            UnauthorizedError (1002): invalid/expired/blacklisted token.
        """
        try:
            payload = decode_token(refresh_token_str)
        except JWTError:
            raise UnauthorizedError()

        if payload.get("type") != "refresh":
            raise UnauthorizedError()

        jti = payload.get("jti")
        user_id = payload.get("sub")

        if not jti or not user_id:
            raise UnauthorizedError()

        # Check blacklist
        if await is_token_blacklisted(jti):
            raise UnauthorizedError()

        # Verify user still exists and is active
        result = await self.db.execute(
            select(User).where(User.id == int(user_id)).limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None or user.deleted_at is not None or user.is_banned:
            raise UnauthorizedError()

        # Issue new access token
        new_jti = str(uuid.uuid4())
        access_token, _ = create_access_token(
            {"sub": str(user.id), "jti": new_jti}
        )

        return {"access_token": access_token}

    # ── Logout ─────────────────────────────────────────────────────

    async def logout(self, refresh_token_str: str) -> None:
        """Blacklist the refresh token so it can't be used again.

        Raises:
            UnauthorizedError (1002): invalid/expired token.
        """
        try:
            payload = decode_token(refresh_token_str)
        except JWTError:
            raise UnauthorizedError()

        if payload.get("type") != "refresh":
            raise UnauthorizedError()

        jti = payload.get("jti")
        exp = payload.get("exp", 0)
        if not jti:
            raise UnauthorizedError()

        await blacklist_refresh_token(jti, exp)

    # ── Get current user ───────────────────────────────────────────

    async def get_me(self, user: User) -> UserInfo:
        """Return the current authenticated user's info."""
        return _user_to_info(user)
