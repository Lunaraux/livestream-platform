"""Custom application exceptions with error codes."""

from typing import Any


class AppException(Exception):
    """Base application exception with error code."""

    def __init__(self, code: int, message: str, status_code: int = 400, detail: Any = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


# ── Auth exceptions ────────────────────────────────────────────────

class InvalidCredentialsError(AppException):
    """Wrong username or password."""

    def __init__(self):
        super().__init__(code=2002, message="用户名或密码错误", status_code=401)


class AccountLockedError(AppException):
    """Account is temporarily locked."""

    def __init__(self):
        super().__init__(code=2003, message="账号已锁定，请稍后重试", status_code=403)


class AccountBannedError(AppException):
    """Account is banned."""

    def __init__(self):
        super().__init__(code=2003, message="账号已封禁", status_code=403)


class UsernameAlreadyExistsError(AppException):
    """Username already taken."""

    def __init__(self):
        super().__init__(code=2001, message="用户名已存在", status_code=409)


class UnauthorizedError(AppException):
    """Not logged in."""

    def __init__(self):
        super().__init__(code=1002, message="未登录", status_code=401)


class ForbiddenError(AppException):
    """No permission."""

    def __init__(self):
        super().__init__(code=1003, message="无权限", status_code=403)


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(self, resource: str = "资源"):
        super().__init__(code=1004, message=f"{resource}不存在", status_code=404)


class ValidationError(AppException):
    """Parameter validation error."""

    def __init__(self, message: str = "参数错误", detail: Any = None):
        super().__init__(code=1001, message=message, status_code=422, detail=detail)


# ── User exceptions ────────────────────────────────────────────────

class CannotFollowSelfError(AppException):
    """Cannot follow yourself."""

    def __init__(self):
        super().__init__(code=1001, message="不能关注自己", status_code=400)


class NotStreamerError(AppException):
    """User is not a streamer."""

    def __init__(self):
        super().__init__(code=1001, message="该用户不是主播", status_code=400)


class AlreadyFollowingError(AppException):
    """Already following this streamer."""

    def __init__(self):
        super().__init__(code=1001, message="已关注该主播", status_code=400)


class NotFollowingError(AppException):
    """Not following this streamer."""

    def __init__(self):
        super().__init__(code=1001, message="未关注该主播", status_code=400)


class WrongPasswordError(AppException):
    """Old password is incorrect."""

    def __init__(self):
        super().__init__(code=2002, message="原密码错误", status_code=400)


class SamePasswordError(AppException):
    """New password same as old."""

    def __init__(self):
        super().__init__(code=1001, message="新密码不能与原密码相同", status_code=400)


class StreamerAlreadyVerifiedError(AppException):
    """Streamer already verified."""

    def __init__(self):
        super().__init__(code=1001, message="主播已通过认证", status_code=400)


class ApplicationAlreadyExistsError(AppException):
    """Streamer application already submitted."""

    def __init__(self):
        super().__init__(code=1001, message="已提交过主播认证申请", status_code=400)


class ApplicationNotFoundError(AppException):
    """Streamer application not found."""

    def __init__(self):
        super().__init__(code=1004, message="认证申请不存在", status_code=404)
