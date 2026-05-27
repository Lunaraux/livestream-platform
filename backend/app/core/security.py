"""JWT token creation/verification, password hashing, and Redis token blacklist."""

from __future__ import annotations

import time
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.redis import get_redis

# ── Password hashing ──────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Invalid plaintext NEVER stored."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare a plaintext password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT ───────────────────────────────────────────────────────────

def _now_utc_ts() -> int:
    return int(time.time())


def create_access_token(data: dict[str, Any]) -> tuple[str, int]:
    """Create an access token (2h expiry).

    Returns (token, expires_at_timestamp).
    """
    now_ts = _now_utc_ts()
    expire_ts = now_ts + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    to_encode = data.copy()
    to_encode.update({"exp": expire_ts, "iat": now_ts, "type": "access"})
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expire_ts


def create_refresh_token(data: dict[str, Any]) -> tuple[str, int]:
    """Create a refresh token (7d expiry).

    Returns (token, expires_at_timestamp).
    """
    now_ts = _now_utc_ts()
    expire_ts = now_ts + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    to_encode = data.copy()
    to_encode.update({"exp": expire_ts, "iat": now_ts, "type": "refresh"})
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expire_ts


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError if invalid/expired."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token. Raises JWTError if type != 'access'."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise JWTError("Token is not an access token")
    return payload


# ── Redis token blacklist ─────────────────────────────────────────


async def blacklist_refresh_token(jti: str, expires_at_ts: int) -> None:
    """Add a refresh token JTI to the Redis blacklist with TTL."""
    r = await get_redis()
    ttl = max(expires_at_ts - _now_utc_ts(), 1)
    await r.setex(f"blacklist:refresh:{jti}", ttl, "1")


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token JTI has been blacklisted."""
    r = await get_redis()
    return await r.exists(f"blacklist:refresh:{jti}") > 0
