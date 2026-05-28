"""Dashboard schemas — admin platform overview and streamer session stats.

Per 08-dashboard.md:
  Admin: realtime overview, trend data, room ranking, user funnel.
  Streamer: live session stats, history comparison.
"""

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
# Admin: platform realtime overview
# ═══════════════════════════════════════════════════════════════════════


class PlatformRealtimeResponse(BaseModel):
    """GET /api/admin/dashboard/realtime — live platform snapshot."""

    online_users: int = Field(default=0, description="当前在线用户数")
    live_rooms: int = Field(default=0, description="当前直播中房间数")
    new_users_today: int = Field(default=0, description="今日新增用户数")
    today_recharge_fen: int = Field(default=0, description="今日充值总额（分）")
    today_gift_fen: int = Field(default=0, description="今日礼物总额（分）")
    danmaku_rate_per_min: int = Field(default=0, description="当前弹幕发送速率（条/分钟）")


# ═══════════════════════════════════════════════════════════════════════
# Admin: trend data
# ═══════════════════════════════════════════════════════════════════════


class DailyTrendItem(BaseModel):
    """One day of trend data."""

    date: str = Field(..., description="日期 YYYY-MM-DD")
    new_users: int = Field(default=0, description="当日新增用户数")
    revenue_fen: int = Field(default=0, description="当日收益（平台+主播分成，分）")
    live_sessions: int = Field(default=0, description="当日开播次数")


class TrendResponse(BaseModel):
    """GET /api/admin/dashboard/trend — trend data for a period."""

    period: str = Field(..., description="周期: 7d / 30d / 90d")
    items: list[DailyTrendItem] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# Admin: room ranking
# ═══════════════════════════════════════════════════════════════════════


class RoomRankItem(BaseModel):
    """One room in the ranking list."""

    room_id: int = Field(..., description="直播间ID")
    title: str = Field(..., description="直播间标题")
    streamer_name: str = Field(..., description="主播昵称")
    category: str = Field(..., description="分类")
    viewer_count: int = Field(default=0, description="当前在线人数")


class RoomRankResponse(BaseModel):
    """GET /api/admin/dashboard/room-rank — current TOP 10 rooms."""

    items: list[RoomRankItem] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# Admin: user growth funnel
# ═══════════════════════════════════════════════════════════════════════


class FunnelResponse(BaseModel):
    """GET /api/admin/dashboard/funnel — user growth funnel."""

    registered_users: int = Field(default=0, description="注册用户总数")
    consuming_users: int = Field(default=0, description="消费用户数（有过消费行为的）")
    active_streamers: int = Field(default=0, description="活跃主播数（通过认证且有直播间）")


# ═══════════════════════════════════════════════════════════════════════
# Streamer: live session stats
# ═══════════════════════════════════════════════════════════════════════


class StreamerLiveResponse(BaseModel):
    """GET /api/streamer/dashboard/live — current live session stats."""

    online_viewers: int = Field(default=0, description="当前在线人数")
    cumulative_viewers: int = Field(default=0, description="累计观看人数")
    danmaku_count: int = Field(default=0, description="弹幕数量")
    like_count: int = Field(default=0, description="点赞数量")
    gift_fen: int = Field(default=0, description="礼物收益（分）")
    word_cloud: list[str] = Field(default_factory=list, description="实时弹幕词云 TOP 20 关键词")


# ═══════════════════════════════════════════════════════════════════════
# Streamer: history comparison
# ═══════════════════════════════════════════════════════════════════════


class HistorySessionItem(BaseModel):
    """One past session for comparison."""

    session_id: int = Field(..., description="场次编号")
    room_id: int = Field(..., description="直播间ID")
    title: str = Field(default="", description="直播间标题")
    duration_minutes: int = Field(default=0, description="直播时长（分钟）")
    peak_viewers: int = Field(default=0, description="峰值在线人数")
    revenue_fen: int = Field(default=0, description="本场收益（分）")
    started_at: str | None = Field(default=None, description="开播时间 ISO 8601")
    ended_at: str | None = Field(default=None, description="结束时间 ISO 8601")


class HistoryResponse(BaseModel):
    """GET /api/streamer/dashboard/history — last 10 sessions comparison."""

    items: list[HistorySessionItem] = Field(default_factory=list)
