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
