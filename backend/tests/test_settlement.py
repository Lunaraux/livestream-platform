"""Tests for settlement service — earnings, withdrawal, admin flow.

Uses in-memory SQLite + mocked Redis (via conftest).

Per 06-settlement.md:
- Platform commission: 30%
- Streamer share: floor(gift_total * 70 / 100)
- Min withdraw: 10000 fen (100 yuan)
- Only one pending withdraw per streamer
"""

import time

import pytest


# ── Test helpers ────────────────────────────────────────────────────


def _register_payload(overrides=None):
    p = {
        "username": "teststreamer",
        "password": "pass1234",
        "nickname": "测试主播",
        "role": "streamer",
    }
    if overrides:
        p.update(overrides)
    return p


async def _register_and_login(client, overrides=None):
    """Register a user and return (response, token, user_id)."""
    r = await client.post("/api/auth/register", json=_register_payload(overrides))
    assert r.status_code == 200
    user_id = r.json()["data"]["id"]

    uname = overrides.get("username", "teststreamer") if overrides else "teststreamer"
    pw = overrides.get("password", "pass1234") if overrides else "pass1234"
    r = await client.post(
        "/api/auth/login",
        json={"username": uname, "password": pw},
    )
    assert r.status_code == 200
    token = r.json()["data"]["access_token"]
    return r, token, user_id


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _prepare_balance(app, streamer_id: int, available_fen: int):
    """Give a streamer available balance for withdrawal testing."""
    from app.core.database import get_db
    from app.services.settlement_service import SettlementService

    gen = app.dependency_overrides[get_db]()
    session = await gen.__anext__()
    try:
        svc = SettlementService(session)
        wallet = await svc._get_or_create_wallet(streamer_id)
        wallet.available_fen = available_fen
        wallet.total_earned_fen = available_fen
        wallet.updated_at = int(time.time())
        await session.commit()
    finally:
        await gen.aclose()


async def _create_room_and_settle(
    app, streamer_id: int, session_amounts: list[int]
) -> int:
    """Create a room, directly insert settlement bills, update wallet.
    Returns the room_id.

    Bypasses the gift-record-based settlement flow for clean unit testing.
    """
    from app.core.database import get_db
    from app.models.room import Room
    from app.models.settlement import PLATFORM_COMMISSION_PCT, SettlementBill, StreamerWallet
    from sqlalchemy import select

    gen = app.dependency_overrides[get_db]()
    session = await gen.__anext__()
    try:
        now = int(time.time())

        # Create room
        room = Room(
            streamer_id=streamer_id,
            title="Test Room",
            category="chat",
            status="idle",
            created_at=now,
            updated_at=now,
        )
        session.add(room)
        await session.flush()

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

        # Create settlement bills and update wallet
        for i, total_gift in enumerate(session_amounts):
            streamer_earn = (total_gift * (100 - PLATFORM_COMMISSION_PCT)) // 100
            platform_fee = total_gift - streamer_earn

            bill = SettlementBill(
                room_id=room.id,
                streamer_id=streamer_id,
                session_id=i + 1,
                total_gift_fen=total_gift,
                platform_fee_fen=platform_fee,
                streamer_earn_fen=streamer_earn,
                settled_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(bill)

            wallet.available_fen += streamer_earn
            wallet.total_earned_fen += streamer_earn
            wallet.updated_at = now

        await session.commit()
        return room.id
    finally:
        await gen.aclose()


# ══════════════════════════════════════════════════════════════════════
# Authorization tests
# ══════════════════════════════════════════════════════════════════════


class TestAuth:
    """Verify that settlement endpoints require authentication and proper roles."""

    @pytest.mark.asyncio
    async def test_earnings_requires_auth(self, client):
        """Unauthenticated request should fail."""
        r = await client.get("/api/streamer/earnings")
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_earnings_requires_streamer_role(self, client):
        """Regular audience cannot access earnings."""
        r = await client.post(
            "/api/auth/register",
            json={
                "username": "normaluser2",
                "password": "pass1234",
                "nickname": "普通用户",
                "role": "audience",
            },
        )
        if r.status_code == 409:
            r = await client.post(
                "/api/auth/login",
                json={"username": "normaluser2", "password": "pass1234"},
            )
            token = r.json()["data"]["access_token"]
        else:
            r = await client.post(
                "/api/auth/login",
                json={"username": "normaluser2", "password": "pass1234"},
            )
            token = r.json()["data"]["access_token"]

        r = await client.get("/api/streamer/earnings", headers=_auth_headers(token))
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_withdraw_requires_auth(self, client):
        """Unauthenticated withdraw should fail."""
        r = await client.post("/api/streamer/withdraw", json={"amount_fen": 10000})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_routes_require_admin(self, client):
        """Regular user cannot access admin endpoints."""
        _, token, _ = await _register_and_login(client)

        r = await client.post(
            "/api/admin/withdraw/1/approve", headers=_auth_headers(token)
        )
        assert r.status_code == 403

        r = await client.post(
            "/api/admin/withdraw/1/reject",
            json={"reject_reason": "test"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 403

        r = await client.get(
            "/api/admin/platform/revenue", headers=_auth_headers(token)
        )
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# Earnings overview tests
# ══════════════════════════════════════════════════════════════════════


class TestEarningsOverview:
    @pytest.mark.asyncio
    async def test_earnings_empty_for_new_streamer(self, client):
        """New streamer should have zero earnings across all fields."""
        _, token, _ = await _register_and_login(client)

        r = await client.get("/api/streamer/earnings", headers=_auth_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["today_earnings_fen"] == 0
        assert data["month_earnings_fen"] == 0
        assert data["total_earned_fen"] == 0
        assert data["available_fen"] == 0
        assert data["pending_fen"] == 0
        assert data["frozen_fen"] == 0

    @pytest.mark.asyncio
    async def test_earnings_after_settlement(self, client, app):
        """Earnings overview should reflect settled amounts."""
        _, token, streamer_id = await _register_and_login(client)

        # Create room and settle 50000 fen of gifts
        await _create_room_and_settle(app, streamer_id, [50000])

        # Now check earnings
        r = await client.get("/api/streamer/earnings", headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        # 50000 * 70 / 100 = 35000
        assert data["today_earnings_fen"] == 35000
        assert data["month_earnings_fen"] == 35000
        assert data["total_earned_fen"] == 35000
        assert data["available_fen"] == 35000
        assert data["pending_fen"] == 0
        assert data["frozen_fen"] == 0


# ══════════════════════════════════════════════════════════════════════
# Earnings detail tests
# ══════════════════════════════════════════════════════════════════════


class TestEarningsDetail:
    @pytest.mark.asyncio
    async def test_detail_empty(self, client):
        """New streamer has no settlement bills."""
        _, token, _ = await _register_and_login(client)

        r = await client.get(
            "/api/streamer/earnings/detail", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_detail_with_bills(self, client, app):
        """Should list settlement bills with pagination."""
        _, token, streamer_id = await _register_and_login(client)

        await _create_room_and_settle(app, streamer_id, [70000, 30000])

        r = await client.get(
            "/api/streamer/earnings/detail", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # Most recent first
        assert data["items"][0]["session_id"] == 2
        assert data["items"][1]["session_id"] == 1

    @pytest.mark.asyncio
    async def test_detail_pagination(self, client, app):
        """Pagination should work correctly."""
        _, token, streamer_id = await _register_and_login(client)

        await _create_room_and_settle(app, streamer_id, [1000, 1000, 1000, 1000, 1000])

        r = await client.get(
            "/api/streamer/earnings/detail?page=1&page_size=2",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_detail_requires_streamer_role(self, client):
        """Audience cannot access earnings detail."""
        r = await client.post(
            "/api/auth/register",
            json={
                "username": "auddetail",
                "password": "pass1234",
                "nickname": "观众",
                "role": "audience",
            },
        )
        if r.status_code == 409:
            r = await client.post(
                "/api/auth/login",
                json={"username": "auddetail", "password": "pass1234"},
            )
            token = r.json()["data"]["access_token"]
        else:
            r = await client.post(
                "/api/auth/login",
                json={"username": "auddetail", "password": "pass1234"},
            )
            token = r.json()["data"]["access_token"]

        r = await client.get(
            "/api/streamer/earnings/detail", headers=_auth_headers(token)
        )
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# Withdraw tests
# ══════════════════════════════════════════════════════════════════════


class TestWithdraw:
    @pytest.mark.asyncio
    async def test_withdraw_success(self, client, app):
        """Successful withdrawal should create a pending request and freeze amount."""
        _, token, streamer_id = await _register_and_login(client)
        await _prepare_balance(app, streamer_id, 50000)

        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 20000},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["amount_fen"] == 20000
        assert data["status"] == "pending"
        assert data["reject_reason"] is None

        # Verify wallet state: available reduced, frozen increased
        r = await client.get("/api/streamer/earnings", headers=_auth_headers(token))
        wallet = r.json()["data"]
        assert wallet["available_fen"] == 30000
        assert wallet["frozen_fen"] == 20000

    @pytest.mark.asyncio
    async def test_withdraw_below_minimum(self, client):
        """Withdraw below 10000 fen should fail with 5001."""
        _, token, _ = await _register_and_login(client)

        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 5000},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422  # Pydantic validation
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_withdraw_insufficient_balance(self, client, app):
        """Withdraw more than available should fail with 4001."""
        _, token, streamer_id = await _register_and_login(client)
        await _prepare_balance(app, streamer_id, 5000)

        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 20000},
            headers=_auth_headers(token),
        )
        # 20000 >= 10000 passes Pydantic, but fails in service with 4001
        assert r.status_code == 400
        assert r.json()["code"] == 4001

    @pytest.mark.asyncio
    async def test_withdraw_exact_minimum(self, client, app):
        """Withdraw exactly 10000 fen should work."""
        _, token, streamer_id = await _register_and_login(client)
        await _prepare_balance(app, streamer_id, 10000)

        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 10000},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_withdraw_duplicate_pending(self, client, app):
        """Cannot submit a second withdrawal while one is pending."""
        _, token, streamer_id = await _register_and_login(client)
        await _prepare_balance(app, streamer_id, 50000)

        # First withdrawal
        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 10000},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200

        # Second withdrawal — should fail with 5002
        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 10000},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 5002

    @pytest.mark.asyncio
    async def test_withdraw_all_available(self, client, app):
        """Withdraw the entire available balance."""
        _, token, streamer_id = await _register_and_login(client)
        await _prepare_balance(app, streamer_id, 30000)

        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 30000},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200

        r = await client.get("/api/streamer/earnings", headers=_auth_headers(token))
        wallet = r.json()["data"]
        assert wallet["available_fen"] == 0
        assert wallet["frozen_fen"] == 30000


# ══════════════════════════════════════════════════════════════════════
# Withdraw history tests
# ══════════════════════════════════════════════════════════════════════


class TestWithdrawHistory:
    @pytest.mark.asyncio
    async def test_history_empty(self, client):
        """New streamer has no withdrawal history."""
        _, token, _ = await _register_and_login(client)

        r = await client.get(
            "/api/streamer/withdraw-history", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_history_with_requests(self, client, app):
        """Should list all withdrawal requests."""
        _, token, streamer_id = await _register_and_login(client)

        await _prepare_balance(app, streamer_id, 50000)

        # Create 1 withdrawal (can only have 1 pending at a time)
        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 10000},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200

        r = await client.get(
            "/api/streamer/withdraw-history", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "pending"
        assert data["items"][0]["amount_fen"] == 10000


# ══════════════════════════════════════════════════════════════════════
# Admin approve/reject tests
# ══════════════════════════════════════════════════════════════════════


class TestAdminWithdraw:
    async def _setup_admin_and_withdraw(self, client, app):
        """Create an admin, a streamer with balance, and a pending withdrawal.
        Returns (admin_token, streamer_token, withdraw_id).
        """
        from app.core.database import get_db
        from app.core.security import hash_password
        from app.models.user import User

        # Create admin directly via DB (role validator restricts public registration)
        gen = app.dependency_overrides[get_db]()
        session = await gen.__anext__()
        try:
            now = int(time.time())
            admin = User(
                username="admin1",
                password_hash=hash_password("admin123"),
                nickname="管理员",
                role="admin",
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            await session.commit()
        finally:
            await gen.aclose()

        # Login as admin
        r = await client.post(
            "/api/auth/login",
            json={"username": "admin1", "password": "admin123"},
        )
        admin_token = r.json()["data"]["access_token"]

        # Register streamer
        _, streamer_token, streamer_id = await _register_and_login(
            client,
            {"username": "str1", "password": "pass1234", "nickname": "主播1", "role": "streamer"},
        )

        # Give balance
        await _prepare_balance(app, streamer_id, 50000)

        # Create withdrawal
        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 15000},
            headers=_auth_headers(streamer_token),
        )
        assert r.status_code == 200
        withdraw_id = r.json()["data"]["id"]

        return admin_token, streamer_token, withdraw_id

    @pytest.mark.asyncio
    async def test_approve_success(self, client, app):
        """Admin can approve a pending withdrawal."""
        admin_token, streamer_token, wid = await self._setup_admin_and_withdraw(
            client, app
        )

        # Verify wallet before
        r = await client.get(
            "/api/streamer/earnings", headers=_auth_headers(streamer_token)
        )
        before = r.json()["data"]
        assert before["frozen_fen"] == 15000

        # Approve
        r = await client.post(
            f"/api/admin/withdraw/{wid}/approve",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "approved"
        assert data["processed_by"] is not None
        assert data["processed_at"] is not None

        # Verify wallet after: frozen released
        r = await client.get(
            "/api/streamer/earnings", headers=_auth_headers(streamer_token)
        )
        after = r.json()["data"]
        assert after["frozen_fen"] == 0
        # available was already reduced when withdraw was created, stays at 35000
        assert after["available_fen"] == 35000

    @pytest.mark.asyncio
    async def test_reject_success(self, client, app):
        """Admin can reject a pending withdrawal."""
        admin_token, streamer_token, wid = await self._setup_admin_and_withdraw(
            client, app
        )

        r = await client.post(
            f"/api/admin/withdraw/{wid}/reject",
            json={"reject_reason": "资料不符"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "rejected"
        assert data["reject_reason"] == "资料不符"

        # Verify wallet: frozen returned to available
        r = await client.get(
            "/api/streamer/earnings", headers=_auth_headers(streamer_token)
        )
        after = r.json()["data"]
        assert after["frozen_fen"] == 0
        assert after["available_fen"] == 50000  # restored

    @pytest.mark.asyncio
    async def test_approve_not_found(self, client, app):
        """Approving non-existent withdrawal should fail."""
        admin_token, _, _ = await self._setup_admin_and_withdraw(client, app)

        r = await client.post(
            "/api/admin/withdraw/99999/approve",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 404
        assert r.json()["code"] == 1004

    @pytest.mark.asyncio
    async def test_approve_already_processed(self, client, app):
        """Cannot approve an already-processed withdrawal."""
        admin_token, _, wid = await self._setup_admin_and_withdraw(client, app)

        # First approve
        await client.post(
            f"/api/admin/withdraw/{wid}/approve",
            headers=_auth_headers(admin_token),
        )

        # Second approve
        r = await client.post(
            f"/api/admin/withdraw/{wid}/approve",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 400
        assert "已处理" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_reject_already_processed(self, client, app):
        """Cannot reject an already-approved withdrawal."""
        admin_token, _, wid = await self._setup_admin_and_withdraw(client, app)

        # First approve
        await client.post(
            f"/api/admin/withdraw/{wid}/approve",
            headers=_auth_headers(admin_token),
        )

        # Try to reject the approved request
        r = await client.post(
            f"/api/admin/withdraw/{wid}/reject",
            json={"reject_reason": "changed mind"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 400
        assert "已处理" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_reject_empty_reason(self, client, app):
        """Rejection without reason should fail validation."""
        admin_token, _, wid = await self._setup_admin_and_withdraw(client, app)

        r = await client.post(
            f"/api/admin/withdraw/{wid}/reject",
            json={"reject_reason": "  "},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_returns_amount_to_available(self, client, app):
        """After rejection, streamer can withdraw the same amount again."""
        admin_token, streamer_token, wid = await self._setup_admin_and_withdraw(
            client, app
        )

        # Reject
        await client.post(
            f"/api/admin/withdraw/{wid}/reject",
            json={"reject_reason": "test"},
            headers=_auth_headers(admin_token),
        )

        # Withdraw again
        r = await client.post(
            "/api/streamer/withdraw",
            json={"amount_fen": 15000},
            headers=_auth_headers(streamer_token),
        )
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Platform revenue tests
# ══════════════════════════════════════════════════════════════════════


class TestPlatformRevenue:
    async def _setup_admin(self, client, app):
        """Create and login as admin (via DB directly)."""
        from app.core.database import get_db
        from app.core.security import hash_password
        from app.models.user import User

        gen = app.dependency_overrides[get_db]()
        session = await gen.__anext__()
        try:
            now = int(time.time())
            admin = User(
                username="padmin",
                password_hash=hash_password("admin123"),
                nickname="平台管理",
                role="admin",
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            await session.commit()
        finally:
            await gen.aclose()

        r = await client.post(
            "/api/auth/login",
            json={"username": "padmin", "password": "admin123"},
        )
        return r.json()["data"]["access_token"]

    @pytest.mark.asyncio
    async def test_revenue_empty(self, client, app):
        """Platform revenue should be zero with no settlements."""
        admin_token = await self._setup_admin(client, app)

        r = await client.get(
            "/api/admin/platform/revenue", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total_platform_revenue_fen"] == 0
        assert data["total_gift_fen"] == 0
        assert data["total_settlements"] == 0

    @pytest.mark.asyncio
    async def test_revenue_with_settlements(self, client, app):
        """Platform revenue should aggregate settlement bills correctly."""
        admin_token = await self._setup_admin(client, app)

        # Create a streamer and settle some bills
        _, _, streamer_id = await _register_and_login(
            client,
            {
                "username": "revstr",
                "password": "pass1234",
                "nickname": "收入主播",
                "role": "streamer",
            },
        )

        await _create_room_and_settle(app, streamer_id, [10000, 20000, 30000])

        r = await client.get(
            "/api/admin/platform/revenue", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total_settlements"] == 3
        assert data["total_gift_fen"] == 60000
        assert data["total_platform_revenue_fen"] == 18000  # 30% of 60000
        assert len(data["items"]) == 1  # all on same day


# ══════════════════════════════════════════════════════════════════════
# Commission calculation tests
# ══════════════════════════════════════════════════════════════════════


class TestCommission:
    @pytest.mark.asyncio
    async def test_commission_split_rounding(self, client, app):
        """Test commission split with values that produce rounding issues (floor division)."""
        from app.models.settlement import PLATFORM_COMMISSION_PCT

        streamer_pct = 100 - PLATFORM_COMMISSION_PCT  # 70

        # 101 fen: floor(101 * 70 / 100) = floor(70.7) = 70
        # platform: 101 - 70 = 31
        streamer_earn = (101 * streamer_pct) // 100
        platform_fee = 101 - streamer_earn
        assert streamer_earn == 70
        assert platform_fee == 31
        assert streamer_earn + platform_fee == 101

        # 99 fen: floor(99 * 70 / 100) = floor(69.3) = 69
        # platform: 99 - 69 = 30
        streamer_earn = (99 * streamer_pct) // 100
        platform_fee = 99 - streamer_earn
        assert streamer_earn == 69
        assert platform_fee == 30
        assert streamer_earn + platform_fee == 99

        # 1 fen: floor(1 * 70 / 100) = 0
        # platform takes all 1 fen
        streamer_earn = (1 * streamer_pct) // 100
        platform_fee = 1 - streamer_earn
        assert streamer_earn == 0
        assert platform_fee == 1

        # 100 fen: perfectly divisible
        streamer_earn = (100 * streamer_pct) // 100
        platform_fee = 100 - streamer_earn
        assert streamer_earn == 70
        assert platform_fee == 30
