"""Dashboard API routes — admin platform overview and streamer session stats.

Per 08-dashboard.md:

Admin routes (require admin role):
  GET /api/admin/dashboard/realtime    Platform realtime overview
  GET /api/admin/dashboard/trend       Platform trend data (7d/30d/90d)
  GET /api/admin/dashboard/room-rank   TOP 10 live rooms by viewers
  GET /api/admin/dashboard/funnel      User growth funnel

Streamer routes (require streamer role):
  GET /api/streamer/dashboard/live     Current live session stats
  GET /api/streamer/dashboard/history  Last 10 sessions comparison
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUserDep, require_role
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.dashboard import (
    FunnelResponse,
    HistoryResponse,
    PlatformRealtimeResponse,
    RoomRankResponse,
    StreamerLiveResponse,
    TrendResponse,
)
from app.services.dashboard_service import DashboardService

admin_router = APIRouter(prefix="/api/admin/dashboard", tags=["dashboard-admin"])
streamer_router = APIRouter(prefix="/api/streamer/dashboard", tags=["dashboard-streamer"])


# ═══════════════════════════════════════════════════════════════════════════
# Admin routes
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/realtime", response_model=ApiResponse[PlatformRealtimeResponse]
)
async def get_platform_realtime(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PlatformRealtimeResponse]:
    """Get platform realtime overview.

    GET /api/admin/dashboard/realtime
    Returns live snapshot: online users, live rooms, today's new users,
    recharge total, gift total, danmaku rate.
    """
    svc = DashboardService(db)
    data = await svc.get_platform_realtime()
    return ApiResponse(code=0, message="success", data=data)


@admin_router.get(
    "/trend", response_model=ApiResponse[TrendResponse]
)
async def get_platform_trend(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    period: str = Query("7d", description="时间周期: 7d / 30d / 90d"),
) -> ApiResponse[TrendResponse]:
    """Get platform trend data.

    GET /api/admin/dashboard/trend?period=7d
    Returns daily new users, revenue, and live session counts for the period.
    """
    svc = DashboardService(db)
    data = await svc.get_trend(period)
    return ApiResponse(code=0, message="success", data=data)


@admin_router.get(
    "/room-rank", response_model=ApiResponse[RoomRankResponse]
)
async def get_room_rank(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RoomRankResponse]:
    """Get TOP 10 live rooms by current viewer count.

    GET /api/admin/dashboard/room-rank
    """
    svc = DashboardService(db)
    data = await svc.get_room_rank()
    return ApiResponse(code=0, message="success", data=data)


@admin_router.get(
    "/funnel", response_model=ApiResponse[FunnelResponse]
)
async def get_user_funnel(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FunnelResponse]:
    """Get user growth funnel: registered → consuming → active streamers.

    GET /api/admin/dashboard/funnel
    """
    svc = DashboardService(db)
    data = await svc.get_funnel()
    return ApiResponse(code=0, message="success", data=data)


# ═══════════════════════════════════════════════════════════════════════════
# Streamer routes
# ═══════════════════════════════════════════════════════════════════════════


@streamer_router.get(
    "/live", response_model=ApiResponse[StreamerLiveResponse]
)
async def get_streamer_live(
    current_user: User = Depends(require_role("streamer")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[StreamerLiveResponse]:
    """Get current live session stats.

    GET /api/streamer/dashboard/live
    Returns online viewers, cumulative viewers, danmaku/like counts,
    gift revenue, and word cloud data.
    """
    svc = DashboardService(db)
    data = await svc.get_streamer_live(current_user)
    return ApiResponse(code=0, message="success", data=data)


@streamer_router.get(
    "/history", response_model=ApiResponse[HistoryResponse]
)
async def get_streamer_history(
    current_user: User = Depends(require_role("streamer")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[HistoryResponse]:
    """Get last 10 sessions comparison.

    GET /api/streamer/dashboard/history
    Returns duration, peak viewers, and revenue for historical sessions.
    """
    svc = DashboardService(db)
    data = await svc.get_streamer_history(current_user)
    return ApiResponse(code=0, message="success", data=data)
