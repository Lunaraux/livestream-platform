"""Tests for currency/wallet service — balance, recharge, transaction history.

Uses in-memory SQLite + mocked Redis.
"""

import pytest


# ── Helpers ────────────────────────────────────────────────────────


def _register_payload(overrides=None):
    p = {
        "username": "testuser",
        "password": "pass1234",
        "nickname": "测试用户",
        "role": "audience",
    }
    if overrides:
        p.update(overrides)
    return p


async def _register_and_login(client, overrides=None):
    """Register a user and return (response, token, user_id)."""
    r = await client.post("/api/auth/register", json=_register_payload(overrides))
    assert r.status_code == 200
    user_id = r.json()["data"]["id"]

    r = await client.post(
        "/api/auth/login",
        json={
            "username": overrides.get("username", "testuser") if overrides else "testuser",
            "password": overrides.get("password", "pass1234") if overrides else "pass1234",
        },
    )
    assert r.status_code == 200
    token = r.json()["data"]["access_token"]
    return r, token, user_id


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Query balance ──────────────────────────────────────────────────


class TestWalletBalance:
    @pytest.mark.asyncio
    async def test_balance_new_user_zero(self, client):
        """Newly registered user should have zero balance."""
        _, token, _ = await _register_and_login(client)
        r = await client.get("/api/wallet/balance", headers=_auth_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["balance_fen"] == 0
        assert body["data"]["frozen_fen"] == 0

    @pytest.mark.asyncio
    async def test_balance_requires_auth(self, client):
        """Unauthenticated request should fail."""
        r = await client.get("/api/wallet/balance")
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_balance_after_recharge(self, client):
        """Balance should reflect after a successful recharge."""
        _, token, _ = await _register_and_login(client)

        # Create and pay recharge (tier 1 = 600 fen)
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        order_id = r.json()["data"]["order_id"]

        # Pay
        r = await client.post(
            f"/api/wallet/recharge/{order_id}/pay",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200

        # Check balance
        r = await client.get("/api/wallet/balance", headers=_auth_headers(token))
        assert r.status_code == 200
        assert r.json()["data"]["balance_fen"] == 600


# ── Create recharge order ──────────────────────────────────────────


class TestRechargeCreate:
    @pytest.mark.asyncio
    async def test_create_order_tier_1(self, client):
        """Tier 1: 600 fen, no bonus."""
        _, token, _ = await _register_and_login(client)
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["total_fen"] == 600
        assert data["order_no"].startswith("RC")
        assert data["payment_url"] == f"/api/wallet/recharge/{data['order_id']}/pay"

    @pytest.mark.asyncio
    async def test_create_order_tier_3(self, client):
        """Tier 3: 6000 + 600 = 6600 fen."""
        _, token, _ = await _register_and_login(client)
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 3},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["total_fen"] == 6600

    @pytest.mark.asyncio
    async def test_create_order_tier_6(self, client):
        """Tier 6: 300000 + 120000 = 420000 fen."""
        _, token, _ = await _register_and_login(client)
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 6},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["total_fen"] == 420000

    @pytest.mark.asyncio
    async def test_create_order_invalid_tier_0(self, client):
        """Tier 0 is invalid."""
        _, token, _ = await _register_and_login(client)
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 0},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_create_order_invalid_tier_7(self, client):
        """Tier 7 does not exist."""
        _, token, _ = await _register_and_login(client)
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 7},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_create_order_requires_auth(self, client):
        """Must be logged in."""
        r = await client.post("/api/wallet/recharge", json={"tier": 1})
        assert r.status_code == 401


# ── Pay recharge order ─────────────────────────────────────────────


class TestRechargePay:
    @pytest.mark.asyncio
    async def test_pay_updates_balance(self, client):
        """Paying a pending order should add to balance."""
        _, token, _ = await _register_and_login(client)

        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 2},  # 3000 + 150 = 3150
            headers=_auth_headers(token),
        )
        order_id = r.json()["data"]["order_id"]

        r = await client.post(
            f"/api/wallet/recharge/{order_id}/pay",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "paid"
        assert body["data"]["total_fen"] == 3150
        assert body["data"]["balance_fen"] == 3150

    @pytest.mark.asyncio
    async def test_pay_updates_balance_multiple(self, client):
        """Multiple recharges should accumulate."""
        _, token, _ = await _register_and_login(client)

        # First recharge
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},  # 600
            headers=_auth_headers(token),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token),
        )

        # Second recharge
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 2},  # 3150
            headers=_auth_headers(token),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token),
        )

        r = await client.get("/api/wallet/balance", headers=_auth_headers(token))
        assert r.json()["data"]["balance_fen"] == 600 + 3150

    @pytest.mark.asyncio
    async def test_pay_already_paid_order(self, client):
        """Paying an already-paid order should fail (idempotent)."""
        _, token, _ = await _register_and_login(client)

        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token),
        )
        order_id = r.json()["data"]["order_id"]

        # Pay first time
        r = await client.post(
            f"/api/wallet/recharge/{order_id}/pay",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200

        # Pay second time
        r = await client.post(
            f"/api/wallet/recharge/{order_id}/pay",
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 1001
        assert "已支付" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_pay_nonexistent_order(self, client):
        """Paying a non-existent order should fail."""
        _, token, _ = await _register_and_login(client)
        r = await client.post(
            "/api/wallet/recharge/99999/pay",
            headers=_auth_headers(token),
        )
        assert r.status_code == 404
        assert r.json()["code"] == 1004

    @pytest.mark.asyncio
    async def test_pay_other_users_order(self, client):
        """Cannot pay another user's order."""
        # User A
        _, token_a, _ = await _register_and_login(
            client, {"username": "usera", "password": "pass1234", "nickname": "用户A"}
        )

        # User A creates order
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token_a),
        )
        order_id = r.json()["data"]["order_id"]

        # User B
        _, token_b, _ = await _register_and_login(
            client, {"username": "userb", "password": "pass1234", "nickname": "用户B"}
        )

        # User B tries to pay User A's order
        r = await client.post(
            f"/api/wallet/recharge/{order_id}/pay",
            headers=_auth_headers(token_b),
        )
        assert r.status_code == 404
        assert r.json()["code"] == 1004

    @pytest.mark.asyncio
    async def test_pay_creates_transaction_record(self, client):
        """A successful payment should create a transaction record."""
        _, token, _ = await _register_and_login(client)

        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token),
        )
        order_id = r.json()["data"]["order_id"]

        # Trace balance before
        bal_before = (await client.get("/api/wallet/balance", headers=_auth_headers(token))).json()["data"]["balance_fen"]

        await client.post(
            f"/api/wallet/recharge/{order_id}/pay",
            headers=_auth_headers(token),
        )

        # Check transactions
        r = await client.get("/api/wallet/transactions", headers=_auth_headers(token))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1

        txn = items[0]
        assert txn["type"] == "recharge"
        assert txn["amount_fen"] == 600
        assert txn["balance_before_fen"] == bal_before
        assert txn["balance_after_fen"] == bal_before + 600
        assert txn["ref_id"] == order_id


# ── Recharge history ───────────────────────────────────────────────


class TestRechargeHistory:
    @pytest.mark.asyncio
    async def test_recharge_history_empty(self, client):
        """New user has no recharge history."""
        _, token, _ = await _register_and_login(client)
        r = await client.get("/api/wallet/recharge-history", headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_recharge_history_after_orders(self, client):
        """Should list all orders including unpaid ones."""
        _, token, _ = await _register_and_login(client)

        # Create 2 orders
        await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token),
        )
        await client.post(
            "/api/wallet/recharge",
            json={"tier": 3},
            headers=_auth_headers(token),
        )

        r = await client.get("/api/wallet/recharge-history", headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # All should be pending
        for item in data["items"]:
            assert item["status"] == "pending"

    @pytest.mark.asyncio
    async def test_recharge_history_pagination(self, client):
        """Pagination should work correctly."""
        _, token, _ = await _register_and_login(client)

        # Create 3 orders
        for tier in [1, 2, 3]:
            await client.post(
                "/api/wallet/recharge",
                json={"tier": tier},
                headers=_auth_headers(token),
            )

        # Page 1
        r = await client.get(
            "/api/wallet/recharge-history?page=1&page_size=2",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1

        # Page 2
        r = await client.get(
            "/api/wallet/recharge-history?page=2&page_size=2",
            headers=_auth_headers(token),
        )
        data = r.json()["data"]
        assert len(data["items"]) == 1
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_recharge_history_requires_auth(self, client):
        """Must be logged in."""
        r = await client.get("/api/wallet/recharge-history")
        assert r.status_code == 401


# ── Transaction ledger ─────────────────────────────────────────────


class TestTransactions:
    @pytest.mark.asyncio
    async def test_transactions_empty(self, client):
        """New user has no transactions."""
        _, token, _ = await _register_and_login(client)
        r = await client.get("/api/wallet/transactions", headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_transactions_after_recharge(self, client):
        """Should see transaction after payment."""
        _, token, _ = await _register_and_login(client)

        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 4},  # 30000 + 6000 = 36000
            headers=_auth_headers(token),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token),
        )

        r = await client.get("/api/wallet/transactions", headers=_auth_headers(token))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["type"] == "recharge"
        assert items[0]["amount_fen"] == 36000
        assert items[0]["balance_before_fen"] == 0
        assert items[0]["balance_after_fen"] == 36000

    @pytest.mark.asyncio
    async def test_transactions_multiple_balance_tracking(self, client):
        """Balance snapshots should be correct across multiple transactions."""
        _, token, _ = await _register_and_login(client)

        # Recharge 1
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},  # 600
            headers=_auth_headers(token),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token),
        )

        # Recharge 2
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 2},  # 3150
            headers=_auth_headers(token),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token),
        )

        r = await client.get("/api/wallet/transactions", headers=_auth_headers(token))
        items = r.json()["data"]["items"]
        assert len(items) == 2

        # Most recent first (id DESC)
        assert items[0]["balance_before_fen"] == 600
        assert items[0]["balance_after_fen"] == 3750

        assert items[1]["balance_before_fen"] == 0
        assert items[1]["balance_after_fen"] == 600

    @pytest.mark.asyncio
    async def test_transactions_type_filter(self, client):
        """Filtering by type should work."""
        _, token, _ = await _register_and_login(client)

        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token),
        )

        # Filter by recharge
        r = await client.get(
            "/api/wallet/transactions?type=recharge",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 1

        # Filter by gift (none exist)
        r = await client.get(
            "/api/wallet/transactions?type=gift",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 0

    @pytest.mark.asyncio
    async def test_transactions_pagination(self, client):
        """Pagination should work for transactions."""
        _, token, _ = await _register_and_login(client)

        # Create and pay 3 recharge orders
        for tier in [1, 2, 3]:
            r = await client.post(
                "/api/wallet/recharge",
                json={"tier": tier},
                headers=_auth_headers(token),
            )
            await client.post(
                f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
                headers=_auth_headers(token),
            )

        r = await client.get(
            "/api/wallet/transactions?page=1&page_size=2",
            headers=_auth_headers(token),
        )
        data = r.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_transactions_requires_auth(self, client):
        """Must be logged in."""
        r = await client.get("/api/wallet/transactions")
        assert r.status_code == 401


# ── Multiple user isolation ────────────────────────────────────────


class TestUserIsolation:
    @pytest.mark.asyncio
    async def test_users_have_separate_balances(self, client):
        """Each user's wallet is independent."""
        # User A
        _, token_a, _ = await _register_and_login(
            client, {"username": "usera", "password": "pass1234", "nickname": "用户A"}
        )
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 3},  # 6600
            headers=_auth_headers(token_a),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token_a),
        )

        # User B
        _, token_b, _ = await _register_and_login(
            client, {"username": "userb", "password": "pass1234", "nickname": "用户B"}
        )

        # User A balance
        r = await client.get("/api/wallet/balance", headers=_auth_headers(token_a))
        assert r.json()["data"]["balance_fen"] == 6600

        # User B balance (should be 0)
        r = await client.get("/api/wallet/balance", headers=_auth_headers(token_b))
        assert r.json()["data"]["balance_fen"] == 0

    @pytest.mark.asyncio
    async def test_transactions_are_user_scoped(self, client):
        """User A cannot see User B's transactions."""
        # User A
        _, token_a, _ = await _register_and_login(
            client, {"username": "usera", "password": "pass1234", "nickname": "用户A"}
        )
        r = await client.post(
            "/api/wallet/recharge",
            json={"tier": 1},
            headers=_auth_headers(token_a),
        )
        await client.post(
            f"/api/wallet/recharge/{r.json()['data']['order_id']}/pay",
            headers=_auth_headers(token_a),
        )

        # User B
        _, token_b, _ = await _register_and_login(
            client, {"username": "userb", "password": "pass1234", "nickname": "用户B"}
        )

        # User B sees empty transactions (not A's)
        r = await client.get("/api/wallet/transactions", headers=_auth_headers(token_b))
        assert len(r.json()["data"]["items"]) == 0

        # User A sees one transaction
        r = await client.get("/api/wallet/transactions", headers=_auth_headers(token_a))
        assert len(r.json()["data"]["items"]) == 1
