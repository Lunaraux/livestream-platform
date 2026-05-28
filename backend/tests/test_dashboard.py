"""Tests for dashboard service — admin platform stats and streamer session analytics.

Uses in-memory SQLite + mocked Redis (via conftest).

Per 08-dashboard.md:
  Admin: realtime, trend, room-rank, funnel.
  Streamer: live session stats, history comparison.
"""

import time

import pytest


# ── Test helpers ────────────────────────────────────────────────────────


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_and_login(
    client, username="testuser", password="pass1234", nickname="测试", role="audience"
):
    """Register a user and return (response, token, user_id)."""
    r = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "nickname": nickname,
            "role": role,
        },
    )
    # Register success or conflict (user already exists)
    if r.status_code == 409:
        pass  # user exists, proceed to login
    else:
        assert r.status_code == 200, f"Register failed: {r.json()}"

    # Login to get token
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, f"Login failed: {r.json()}"
    data = r.json()["data"]
    token = data["access_token"]
    user_id = data["user_info"]["id"]
    return r, token, user_id


async def _create_admin(client):
    """Create an admin user directly in DB (admin cannot register via API)
    and return (user_data dict, token)."""
    import uuid
    from app.core.security import create_access_token, hash_password
    from app.models.user import User
    from tests.conftest import test_session_factory

    admin_name = f"a{int(time.time() * 1000) % 1000000000}"
    async with test_session_factory() as session:
        now = int(time.time())
        admin = User(
            username=admin_name,
            password_hash=hash_password("admin1234"),
            nickname="管理员",
            role="admin",
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        access_token, _ = create_access_token(
            {"sub": str(admin.id), "jti": str(uuid.uuid4())}
        )
        return {"id": admin.id, "username": admin_name}, access_token


async def _register_streamer(client, username="teststreamer"):
    """Register and login as streamer."""
    return await _register_and_login(
        client,
        username=username,
        password="pass1234",
        nickname="测试主播",
        role="streamer",
    )


async def _create_room(app, streamer_id: int, status="live", title="测试直播间") -> int:
    """Create a room directly in DB."""
    from app.core.database import get_db
    from app.models.room import Room

    gen = app.dependency_overrides[get_db]()
    session = await gen.__anext__()
    try:
        now = int(time.time())
        room = Room(
            streamer_id=streamer_id,
            title=title,
            category="chat",
            status=status,
            peak_viewers=100,
            total_sessions=1,
            started_at=now - 3600,
            ended_at=now if status != "live" else None,
            created_at=now - 3600,
            updated_at=now,
        )
        session.add(room)
        await session.flush()
        room_id = room.id
        await session.commit()
        return room_id
    finally:
        await gen.aclose()


async def _add_settlement_bills(app, streamer_id: int, room_id: int, amounts: list[int]):
    """Add settlement bills directly in DB."""
    from app.core.database import get_db
    from app.models.settlement import PLATFORM_COMMISSION_PCT, SettlementBill, StreamerWallet
    from sqlalchemy import select

    gen = app.dependency_overrides[get_db]()
    session = await gen.__anext__()
    try:
        now = int(time.time())

        # Get or create wallet
        wallet = (await session.execute(
            select(StreamerWallet).where(
                StreamerWallet.streamer_id == streamer_id,
                StreamerWallet.deleted_at.is_(None),
            )
        )).scalar_one_or_none()

        if wallet is None:
            wallet = StreamerWallet(
                streamer_id=streamer_id,
                pending_fen=0,
                available_fen=0,
                frozen_fen=0,
                total_earned_fen=0,
                created_at=now,
                updated_at=now,
            )
            session.add(wallet)
            await session.flush()

        for i, total_gift in enumerate(amounts):
            streamer_earn = (total_gift * (100 - PLATFORM_COMMISSION_PCT)) // 100
            platform_fee = total_gift - streamer_earn

            bill = SettlementBill(
                room_id=room_id,
                streamer_id=streamer_id,
                session_id=i + 1,
                total_gift_fen=total_gift,
                platform_fee_fen=platform_fee,
                streamer_earn_fen=streamer_earn,
                settled_at=now - (len(amounts) - i) * 86400,  # spread across days
                created_at=now,
                updated_at=now,
            )
            session.add(bill)

            wallet.available_fen += streamer_earn
            wallet.total_earned_fen += streamer_earn
            wallet.updated_at = now

        await session.commit()
    finally:
        await gen.aclose()


async def _add_gift_records(app, room_id: int, total_fen: int, count: int = 1):
    """Add gift records directly in DB."""
    from app.core.database import get_db
    from app.models.interaction import GiftRecord

    gen = app.dependency_overrides[get_db]()
    session = await gen.__anext__()
    try:
        now = int(time.time())
        per_record = total_fen // count
        remainder = total_fen - per_record * count

        for i in range(count):
            extra = remainder if i == 0 else 0
            record = GiftRecord(
                room_id=room_id,
                sender_id=1,  # dummy sender
                receiver_id=1,  # dummy receiver
                gift_id=1,  # dummy gift
                quantity=1,
                total_amount_fen=per_record + extra,
                gift_name="测试礼物",
                gift_effect="normal",
                created_at=now,
                updated_at=now,
            )
            session.add(record)

        await session.commit()
    finally:
        await gen.aclose()


async def _add_danmaku(app, room_id: int, contents: list[str]):
    """Add danmaku records directly in DB."""
    from app.core.database import get_db
    from app.models.interaction import Danmaku

    gen = app.dependency_overrides[get_db]()
    session = await gen.__anext__()
    try:
        now = int(time.time())
        for content in contents:
            dm = Danmaku(
                room_id=room_id,
                user_id=1,
                content=content,
                color="#FFFFFF",
                created_at=now,
                updated_at=now,
            )
            session.add(dm)

        await session.commit()
    finally:
        await gen.aclose()


async def _add_recharge_order(app, user_id: int, total_fen: int):
    """Add a paid recharge order directly in DB."""
    from app.core.database import get_db
    from app.models.currency import RechargeOrder

    gen = app.dependency_overrides[get_db]()
    session = await gen.__anext__()
    try:
        now = int(time.time())
        order = RechargeOrder(
            order_no=f"TEST-{now}-{user_id}",
            user_id=user_id,
            tier=1,
            recharge_fen=total_fen,
            bonus_fen=0,
            total_fen=total_fen,
            status="paid",
            paid_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(order)
        await session.commit()
    finally:
        await gen.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# Authorization tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """Verify dashboard endpoints require authentication and proper roles."""

    @pytest.mark.asyncio
    async def test_admin_realtime_requires_auth(self, client):
        r = await client.get("/api/admin/dashboard/realtime")
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_admin_realtime_requires_admin(self, client):
        _, token, _ = await _register_streamer(client, "audience1")
        r = await client.get(
            "/api/admin/dashboard/realtime", headers=_auth_headers(token)
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_trend_requires_admin(self, client):
        _, token, _ = await _register_streamer(client, "audience2")
        r = await client.get(
            "/api/admin/dashboard/trend", headers=_auth_headers(token)
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_room_rank_requires_admin(self, client):
        _, token, _ = await _register_streamer(client, "audience3")
        r = await client.get(
            "/api/admin/dashboard/room-rank", headers=_auth_headers(token)
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_funnel_requires_admin(self, client):
        _, token, _ = await _register_streamer(client, "audience4")
        r = await client.get(
            "/api/admin/dashboard/funnel", headers=_auth_headers(token)
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_streamer_live_requires_auth(self, client):
        r = await client.get("/api/streamer/dashboard/live")
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_streamer_live_requires_streamer(self, client):
        _, token = await _create_admin(client)
        r = await client.get(
            "/api/streamer/dashboard/live", headers=_auth_headers(token)
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_streamer_history_requires_streamer(self, client):
        _, token = await _create_admin(client)
        r = await client.get(
            "/api/streamer/dashboard/history", headers=_auth_headers(token)
        )
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Admin: Realtime tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminRealtime:
    @pytest.mark.asyncio
    async def test_realtime_empty(self, client):
        """Empty platform should return zeros for all fields."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/realtime", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["online_users"] == 0
        assert data["live_rooms"] == 0
        assert data["new_users_today"] >= 0
        assert data["today_recharge_fen"] == 0
        assert data["today_gift_fen"] == 0
        assert data["danmaku_rate_per_min"] == 0

    @pytest.mark.asyncio
    async def test_realtime_with_data(self, client, app):
        """Realtime should reflect live rooms, new users, and today's activity."""
        _, admin_token = await _create_admin(client)

        # Register a streamer and create a live room
        _, streamer_token, streamer_id = await _register_streamer(client)
        room_id = await _create_room(app, streamer_id, status="live")

        # Add gifts and danmaku
        await _add_gift_records(app, room_id, 50000)
        await _add_danmaku(app, room_id, ["大家好", "主播加油"])

        # Add recharge
        await _add_recharge_order(app, streamer_id, 30000)

        r = await client.get(
            "/api/admin/dashboard/realtime", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["live_rooms"] == 1
        assert data["today_gift_fen"] == 50000
        assert data["today_recharge_fen"] == 30000
        # new_users_today should include at least the admin + streamer
        assert data["new_users_today"] >= 2


# ═══════════════════════════════════════════════════════════════════════════
# Admin: Trend tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminTrend:
    @pytest.mark.asyncio
    async def test_trend_empty(self, client):
        """Empty platform should return zero-filled trend items."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/trend?period=7d", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["period"] == "7d"
        assert len(data["items"]) == 7
        for item in data["items"]:
            assert item["new_users"] >= 0
            assert item["revenue_fen"] >= 0
            assert item["live_sessions"] >= 0

    @pytest.mark.asyncio
    async def test_trend_30d(self, client):
        """Should accept 30d period."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/trend?period=30d", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["period"] == "30d"
        assert len(data["items"]) == 30

    @pytest.mark.asyncio
    async def test_trend_90d(self, client):
        """Should accept 90d period."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/trend?period=90d", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["period"] == "90d"
        assert len(data["items"]) == 90

    @pytest.mark.asyncio
    async def test_trend_invalid_period(self, client):
        """Invalid period should fail with validation error."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/trend?period=invalid",
            headers=_auth_headers(token),
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_trend_default_period(self, client):
        """Default period should be 7d."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/trend", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["period"] == "7d"

    @pytest.mark.asyncio
    async def test_trend_with_settlement(self, client, app):
        """Trend should reflect settlement bills."""
        _, admin_token = await _create_admin(client)
        _, streamer_token, streamer_id = await _register_streamer(client)
        room_id = await _create_room(app, streamer_id, status="ended")

        # Add settlement bills spread across days
        await _add_settlement_bills(app, streamer_id, room_id, [100000, 50000])

        r = await client.get(
            "/api/admin/dashboard/trend?period=7d", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        total_revenue = sum(item["revenue_fen"] for item in data["items"])
        total_sessions = sum(item["live_sessions"] for item in data["items"])
        assert total_revenue == 150000
        assert total_sessions == 2


# ═══════════════════════════════════════════════════════════════════════════
# Admin: Room Rank tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminRoomRank:
    @pytest.mark.asyncio
    async def test_room_rank_empty(self, client):
        """Empty platform should return empty rank list."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/room-rank", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_room_rank_with_live_rooms(self, client, app):
        """Should return live rooms sorted by viewer count (from Redis, which is 0 in mock)."""
        _, admin_token = await _create_admin(client)

        # Create two live rooms
        _, _, s1 = await _register_streamer(client, "streamer_a")
        _, _, s2 = await _register_streamer(client, "streamer_b")
        await _create_room(app, s1, status="live", title="直播间A")
        await _create_room(app, s2, status="live", title="直播间B")

        r = await client.get(
            "/api/admin/dashboard/room-rank", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["items"]) == 2
        titles = {item["title"] for item in data["items"]}
        assert "直播间A" in titles
        assert "直播间B" in titles

    @pytest.mark.asyncio
    async def test_room_rank_excludes_non_live(self, client, app):
        """Should only include live rooms (not idle/ended/banned)."""
        _, admin_token = await _create_admin(client)

        _, _, s = await _register_streamer(client, "streamer_c")
        await _create_room(app, s, status="idle", title="未开播")

        r = await client.get(
            "/api/admin/dashboard/room-rank", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        titles = {item["title"] for item in data["items"]}
        assert "未开播" not in titles


# ═══════════════════════════════════════════════════════════════════════════
# Admin: Funnel tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminFunnel:
    @pytest.mark.asyncio
    async def test_funnel_empty(self, client):
        """Empty platform should return zeros."""
        _, token = await _create_admin(client)

        r = await client.get(
            "/api/admin/dashboard/funnel", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["registered_users"] >= 0
        assert data["consuming_users"] == 0
        assert data["active_streamers"] == 0

    @pytest.mark.asyncio
    async def test_funnel_with_data(self, client, app):
        """Funnel should count registered, consuming, and active streamer users."""
        _, admin_token = await _create_admin(client)

        # Create a streamer with a room (active streamer)
        _, _, streamer_id = await _register_streamer(client, "streamer_x")
        await _create_room(app, streamer_id, status="idle")

        # Manually set streamer_verified=True (registration API doesn't auto-verify)
        from app.core.database import get_db
        from app.models.user import User
        from sqlalchemy import select
        gen = app.dependency_overrides[get_db]()
        session = await gen.__anext__()
        try:
            result = await session.execute(
                select(User).where(User.id == streamer_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.streamer_verified = True
                await session.commit()
        finally:
            await gen.aclose()

        # Create a regular audience user
        _, _, _ = await _register_and_login(
            client,
            username="consumer1",
            password="pass1234",
            nickname="消费用户",
            role="audience",
        )

        # Make consumer have spent coins
        from app.core.database import get_db
        from app.models.user import User
        from sqlalchemy import select

        gen = app.dependency_overrides[get_db]()
        session = await gen.__anext__()
        try:
            result = await session.execute(
                select(User).where(User.username == "consumer1")
            )
            user = result.scalar_one_or_none()
            if user:
                user.total_consumed_fen = 10000
                await session.commit()
        finally:
            await gen.aclose()

        r = await client.get(
            "/api/admin/dashboard/funnel", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["registered_users"] >= 3  # admin + streamer + consumer
        assert data["consuming_users"] >= 1    # consumer has spent
        assert data["active_streamers"] >= 1   # streamer with room


# ═══════════════════════════════════════════════════════════════════════════
# Streamer: Live session tests
# ═══════════════════════════════════════════════════════════════════════════


class TestStreamerLive:
    @pytest.mark.asyncio
    async def test_live_no_active_room(self, client):
        """Streamer without a live room should get zeros."""
        _, token, _ = await _register_streamer(client)

        r = await client.get(
            "/api/streamer/dashboard/live", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["online_viewers"] == 0
        assert data["cumulative_viewers"] == 0
        assert data["danmaku_count"] == 0
        assert data["like_count"] == 0
        assert data["gift_fen"] == 0
        assert data["word_cloud"] == []

    @pytest.mark.asyncio
    async def test_live_with_active_room(self, client, app):
        """Streamer with a live room should get session stats."""
        _, token, streamer_id = await _register_streamer(client)
        room_id = await _create_room(app, streamer_id, status="live", title="我的直播间")

        # Add some danmaku
        await _add_danmaku(
            app, room_id,
            ["大家好", "欢迎来到直播间", "主播真厉害", "加油加油", "太精彩了",
             "主播加油", "666", "哈哈哈哈", "来了来了", "支持主播"],
        )

        # Add gifts
        await _add_gift_records(app, room_id, 30000)

        r = await client.get(
            "/api/streamer/dashboard/live", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["danmaku_count"] == 10
        assert data["gift_fen"] == 30000
        assert len(data["word_cloud"]) > 0

    @pytest.mark.asyncio
    async def test_live_word_cloud(self, client, app):
        """Word cloud should extract frequent keywords from danmaku."""
        _, token, streamer_id = await _register_streamer(client)
        room_id = await _create_room(app, streamer_id, status="live")

        # Add same phrase many times to ensure it appears in word cloud
        danmaku_list = (["主播加油"] * 20) + (["精彩"] * 15) + (["666"] * 10) + ["一般"]
        await _add_danmaku(app, room_id, danmaku_list)

        r = await client.get(
            "/api/streamer/dashboard/live", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["word_cloud"]) > 0
        word_cloud_str = " ".join(data["word_cloud"])
        assert "主播" in word_cloud_str or "加油" in word_cloud_str or "精彩" in word_cloud_str or "666" in word_cloud_str


# ═══════════════════════════════════════════════════════════════════════════
# Streamer: History tests
# ═══════════════════════════════════════════════════════════════════════════


class TestStreamerHistory:
    @pytest.mark.asyncio
    async def test_history_empty(self, client):
        """New streamer with no sessions should get empty list."""
        _, token, _ = await _register_streamer(client)

        r = await client.get(
            "/api/streamer/dashboard/history", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_history_with_sessions(self, client, app):
        """Should return last 10 sessions with duration, peak, revenue."""
        _, token, streamer_id = await _register_streamer(client)

        room_id = await _create_room(app, streamer_id, status="ended", title="历史直播间")
        await _add_settlement_bills(app, streamer_id, room_id, [100000, 50000, 20000])

        r = await client.get(
            "/api/streamer/dashboard/history", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["room_id"] == room_id
            assert item["title"] == "历史直播间"
            assert item["revenue_fen"] > 0
            assert item["session_id"] >= 1

    @pytest.mark.asyncio
    async def test_history_max_10(self, client, app):
        """Should cap at 10 sessions."""
        _, token, streamer_id = await _register_streamer(client)

        room_id = await _create_room(app, streamer_id, status="ended")
        await _add_settlement_bills(app, streamer_id, room_id, [10000] * 12)

        r = await client.get(
            "/api/streamer/dashboard/history", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["items"]) == 10  # capped at 10

    @pytest.mark.asyncio
    async def test_history_other_streamer_not_visible(self, client, app):
        """Streamer should only see their own history."""
        _, token1, s1 = await _register_streamer(client, "streamer_one")
        _, token2, s2 = await _register_streamer(client, "streamer_two")

        room1 = await _create_room(app, s1, status="ended", title="主播1的房间")
        room2 = await _create_room(app, s2, status="ended", title="主播2的房间")

        await _add_settlement_bills(app, s1, room1, [50000])
        await _add_settlement_bills(app, s2, room2, [100000])

        r = await client.get(
            "/api/streamer/dashboard/history", headers=_auth_headers(token1)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["revenue_fen"] == 50000
