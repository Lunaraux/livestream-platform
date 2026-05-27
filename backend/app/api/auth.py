"""Auth API routes — register, login, refresh, logout, me."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUserDep
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, TokenRefreshRequest, UserInfo
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[UserInfo])
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ApiResponse[UserInfo]:
    """Register a new user account.

    POST /api/auth/register
    - username: 4-20 chars, alphanumeric + underscore
    - password: 8-20 chars, must include letter + digit
    - nickname: 2-20 chars
    - role: audience | streamer

    Error codes: 2001 (username exists)
    """
    svc = AuthService(db)
    user_info = await svc.register(
        username=body.username,
        password=body.password,
        nickname=body.nickname,
        role=body.role,
    )
    return ApiResponse(code=0, message="注册成功", data=user_info)


@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ApiResponse[LoginResponse]:
    """Login and receive access + refresh tokens.

    POST /api/auth/login
    - access_token: valid for 2 hours
    - refresh_token: valid for 7 days
    - 5 consecutive failures → 30-minute lock

    Error codes: 2002 (wrong credentials), 2003 (locked/banned)
    """
    client_ip = request.client.host if request.client else None
    svc = AuthService(db)
    result = await svc.login(
        username=body.username,
        password=body.password,
        ip_address=client_ip,
    )
    return ApiResponse(code=0, message="登录成功", data=result)


@router.post("/refresh", response_model=ApiResponse[dict])
async def refresh_token(
    body: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ApiResponse[dict]:
    """Refresh an access token using a valid refresh token.

    POST /api/auth/refresh
    - Returns a new access_token

    Error codes: 1002 (invalid/expired/blacklisted token)
    """
    svc = AuthService(db)
    result = await svc.refresh(body.refresh_token)
    return ApiResponse(code=0, message="success", data=result)


@router.post("/logout", response_model=ApiResponse[None])
async def logout(
    body: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ApiResponse[None]:
    """Logout by blacklisting the refresh token.

    POST /api/auth/logout
    - Blacklists refresh_token in Redis (TTL = remaining validity)
    """
    svc = AuthService(db)
    await svc.logout(body.refresh_token)
    return ApiResponse(code=0, message="已登出", data=None)


@router.get("/me", response_model=ApiResponse[UserInfo])
async def get_me(
    current_user: CurrentUserDep,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ApiResponse[UserInfo]:
    """Return the currently authenticated user's info.

    GET /api/auth/me
    - Requires Authorization: Bearer <access_token>

    Error codes: 1002 (not logged in), 2003 (banned/locked)
    """
    svc = AuthService(db)
    user_info = await svc.get_me(current_user)
    return ApiResponse(code=0, message="success", data=user_info)
