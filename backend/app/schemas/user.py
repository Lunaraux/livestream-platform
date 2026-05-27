"""User schemas — request/response models for user profiles, follow, ban, streamer verify."""

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.auth import UserInfo


# ── Level system ───────────────────────────────────────────────────
# Per 02-user.md: cumulative consumption determines level

LEVEL_THRESHOLDS = {
    1: 0,
    2: 10000,     # 100 yuan
    3: 50000,     # 500 yuan
    4: 200000,    # 2000 yuan
    5: 500000,    # 5000 yuan
    6: 2000000,   # 20000 yuan
}

LEVEL_NAMES = {
    1: "普通观众",
    2: "铁牌粉丝",
    3: "铜牌粉丝",
    4: "银牌粉丝",
    5: "金牌粉丝",
    6: "钻石粉丝",
}


def calculate_level(total_consumed_fen: int) -> int:
    """Derive audience level from cumulative consumption."""
    level = 1
    for lv in sorted(LEVEL_THRESHOLDS.keys()):
        if total_consumed_fen >= LEVEL_THRESHOLDS[lv]:
            level = lv
    return level


# ── Request schemas ────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    """Update personal profile. All fields optional — only provided fields are updated."""

    nickname: str | None = Field(default=None, min_length=2, max_length=20)
    avatar_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    """Change password — must provide old password."""

    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=20)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        import re
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("新密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("新密码必须包含数字")
        return v


class BanUserRequest(BaseModel):
    """Admin: ban a user."""

    reason: str = Field(..., min_length=1, max_length=500, description="封禁原因")
    duration_hours: int = Field(default=0, ge=0, description="封禁时长（小时），0=永久")


class VerifyStreamerRequest(BaseModel):
    """Admin: approve or reject a streamer application."""

    approved: bool = Field(..., description="是否通过认证")
    reject_reason: str | None = Field(default=None, max_length=500, description="拒绝原因（拒绝时必填）")

    @model_validator(mode="after")
    def check_reject_reason(self):
        if not self.approved and not self.reject_reason:
            raise ValueError("拒绝时必须提供拒绝原因")
        return self


class ApplyStreamerRequest(BaseModel):
    """Apply for streamer verification."""

    real_name: str = Field(..., min_length=2, max_length=50, description="真实姓名")
    id_number: str = Field(..., min_length=15, max_length=18, description="身份证号")


# ── Response schemas ───────────────────────────────────────────────

class UserPublicProfile(UserInfo):
    """Extended public profile with follower stats and follow status."""

    bio: str | None = None
    follower_count: int = 0
    following_count: int = 0
    is_following: bool = False  # Only meaningful when viewer is authenticated
    level_name: str = "普通观众"

    model_config = {"from_attributes": True}


class FollowingItem(BaseModel):
    """A streamer I'm following."""

    id: int
    username: str
    nickname: str
    avatar_url: str | None = None
    bio: str | None = None
    is_live: bool = False  # Whether the streamer's room is currently live

    model_config = {"from_attributes": True}


class FollowerItem(BaseModel):
    """A user who follows me (only visible to streamers)."""

    id: int
    username: str
    nickname: str
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


class FollowStatus(BaseModel):
    """Result of a follow/unfollow action."""

    is_following: bool
    message: str


class StreamerApplicationInfo(BaseModel):
    """Streamer application details (for admin review)."""

    id: int
    user_id: int
    real_name: str
    id_number: str  # Already masked
    status: str
    reject_reason: str | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
