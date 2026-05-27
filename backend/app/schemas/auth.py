"""Auth schemas — request/response models for registration, login, token refresh."""

import re

from pydantic import BaseModel, Field, field_validator


# ── Request schemas ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """Registration request.

    Validation per 01-auth.md:
    - username: 4-20 chars, alphanumeric + underscore
    - password: 8-20 chars, must contain letter + digit
    - nickname: 2-20 chars
    - role: audience or streamer
    """

    username: str = Field(..., min_length=4, max_length=20)
    password: str = Field(..., min_length=8, max_length=20)
    nickname: str = Field(..., min_length=2, max_length=20)
    role: str = Field(default="audience")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_]+", v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含数字")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("audience", "streamer"):
            raise ValueError("角色只能是 audience 或 streamer")
        return v


class LoginRequest(BaseModel):
    """Login request."""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenRefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str = Field(..., min_length=1)


# ── Response schemas ───────────────────────────────────────────────

class UserInfo(BaseModel):
    """Public user information returned in API responses.

    Timestamps are returned as ISO 8601 strings per 00-global.md.
    """

    id: int
    username: str
    nickname: str
    avatar_url: str | None = None
    role: str
    level: int
    streamer_verified: bool
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Successful login response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_info: UserInfo
