"""Tests for interaction service — danmaku, like, gift, forbidden words.

Uses in-memory SQLite + mocked Redis.
"""

import time
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.interaction import Gift
from app.models.user import User, Wallet
from tests.conftest import test_session_factory


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


async def _register(client, overrides=None):
    r = await client.post("/api/auth/register", json=_register_payload(overrides))
    return r


async def _login(client, username="testuser", password="pass1234"):
    r = await client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    return r


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_and_login(client, overrides=None):
    reg = await _register(client, overrides)
    username = overrides.get("username", "testuser") if overrides else "testuser"
    password = overrides.get("password", "pass1234") if overrides else "pass1234"
    login = await _login(client, username, password)
    return reg.json()["data"], login.json()["data"]["access_token"]


async def _create_verified_streamer(client) -> tuple[dict, str]:
    """Create a verified streamer."""
    uname = f"s{int(time.time()*1000) % 1000000000}"
    user_data, token = await _register_and_login(
        client, {"username": uname, "role": "streamer"}
    )

    async with test_session_factory() as session:
        result = await session.execute(
            __import__("sqlalchemy").select(User).where(User.id == user_data["id"])
        )
        user = result.scalar_one()
        user.streamer_verified = True
        await session.commit()

    return user_data, token


async def _create_admin(client) -> tuple[dict, str]:
    """Create an admin user directly in DB."""
    admin_name = f"a{int(time.time()*1000) % 1000000000}"
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


async def _create_room(client, token: str, overrides=None) -> dict:
    payload = {
        "title": "测试直播间",
        "description": "这是一个测试直播间",
        "category": "game",
        "cover_url": "https://example.com/cover.jpg",
    }
    if overrides:
        payload.update(overrides)
    r = await client.post("/api/rooms", json=payload, headers=_auth_headers(token))
    return r.json()["data"]


async def _start_stream(client, token: str, room_id: int) -> dict:
    r = await client.post(
        f"/api/rooms/{room_id}/start", headers=_auth_headers(token)
    )
    return r.json()["data"]


async def _setup_live_room(client) -> tuple[dict, str, dict]:
    """Create a verified streamer, create room, start streaming.

    Returns (streamer_data, streamer_token, room_data).
    """
    streamer_data, token = await _create_verified_streamer(client)
    room = await _create_room(client, token)
    await _start_stream(client, token, room["id"])
    return streamer_data, token, room


async def _top_up_wallet(user_id: int, amount_fen: int) -> None:
    """Add balance to a user's wallet."""
    async with test_session_factory() as session:
        result = await session.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet:
            wallet.balance_fen += amount_fen
            await session.commit()
        else:
            now = int(time.time())
            wallet = Wallet(
                user_id=user_id,
                balance_fen=amount_fen,
                created_at=now,
                updated_at=now,
            )
            session.add(wallet)
            await session.commit()


async def _seed_default_gifts() -> None:
    """Insert the default gift catalog from spec 04-interaction.md."""
    gifts = [
        ("小星星", 100, "normal"),
        ("爱心", 500, "normal"),
        ("火箭", 5000, "fullscreen"),
        ("超级星舰", 50000, "announcement"),
        ("守护船票", 198000, "guardian"),
    ]
    async with test_session_factory() as session:
        now = int(time.time())
        for name, price, effect in gifts:
            # Check if exists
            existing = await session.execute(
                select(Gift).where(Gift.name == name, Gift.deleted_at.is_(None))
            )
            if existing.scalar_one_or_none():
                continue
            gift = Gift(
                name=name,
                price_fen=price,
                effect=effect,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(gift)
        await session.commit()


async def _add_forbidden_word(word: str) -> None:
    """Insert a forbidden word directly in DB."""
    from app.models.interaction import ForbiddenWord

    async with test_session_factory() as session:
        now = int(time.time())
        fw = ForbiddenWord(word=word, created_at=now, updated_at=now)
        session.add(fw)
        await session.commit()


# ── Danmaku Tests ──────────────────────────────────────────────────


class TestSendDanmaku:
    @pytest.mark.asyncio
    async def test_send_danmaku_success(self, client):
        """Audience can send danmaku in a live room."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "aud1", "role": "audience"}
        )

        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "大家好！", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["content"] == "大家好！"
        assert body["data"]["color"] == "#FFFFFF"
        assert body["data"]["username"] == "aud1"
        assert body["data"]["is_pinned"] is False
        assert body["data"]["pin_duration_seconds"] is None
        # Timestamp is ISO 8601
        datetime.fromisoformat(body["data"]["created_at"])

    @pytest.mark.asyncio
    async def test_send_danmaku_unauthorized(self, client):
        """Unauthenticated users cannot send danmaku."""
        _, _, room = await _setup_live_room(client)

        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "test", "color": "#FFFFFF"},
        )
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_send_danmaku_room_not_live(self, client):
        """Cannot send danmaku in a non-live room."""
        _, token = await _create_verified_streamer(client)
        room = await _create_room(client, token)  # idle state
        user_data, aud_token = await _register_and_login(
            client, {"username": "aud2", "role": "audience"}
        )

        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "test", "color": "#FFFFFF"},
            headers=_auth_headers(aud_token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 3002

    @pytest.mark.asyncio
    async def test_send_danmaku_color_validation(self, client):
        """Low-level users can only use white danmaku."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "lowlevel", "role": "audience"}
        )

        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "test", "color": "#FF0000"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001
        assert "颜色" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_send_danmaku_content_too_long(self, client):
        """Content must be <= 100 characters."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "aud3", "role": "audience"}
        )

        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "A" * 101, "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_send_danmaku_forbidden_word(self, client):
        """Danmaku with forbidden word is rejected."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "aud4", "role": "audience"}
        )
        await _add_forbidden_word("敏感词")

        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "包含敏感词的弹幕", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 1001
        assert "违禁词" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_send_danmaku_rate_limit(self, client):
        """Rate limit: max 3 per 5 seconds per user per room."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "spammer", "role": "audience"}
        )

        # Send 3 danmaku quickly — should succeed
        for i in range(3):
            r = await client.post(
                f"/api/rooms/{room['id']}/danmaku",
                json={"content": f"弹幕{i+1}", "color": "#FFFFFF"},
                headers=_auth_headers(token),
            )
            assert r.status_code == 200

        # 4th request within window should fail
        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "弹幕4", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 429
        assert r.json()["code"] == 1001
        assert "频率" in r.json()["message"]


# ── Danmaku History Tests ─────────────────────────────────────────


class TestGetDanmakuHistory:
    @pytest.mark.asyncio
    async def test_get_history_empty(self, client):
        """Get history from a room with no danmaku."""
        _, _, room = await _setup_live_room(client)

        r = await client.get(f"/api/rooms/{room['id']}/danmaku")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_get_history_with_danmaku(self, client):
        """Get history returns sent danmaku, newest first."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "historyaud", "role": "audience"}
        )

        # Send 2 danmaku
        await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "第一条", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )
        await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "第二条", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )

        r = await client.get(f"/api/rooms/{room['id']}/danmaku")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert len(body["data"]) == 2
        # Newest first
        assert body["data"][0]["content"] == "第二条"
        assert body["data"][1]["content"] == "第一条"

    @pytest.mark.asyncio
    async def test_get_history_no_auth_required(self, client):
        """Danmaku history is accessible without login."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "publicaud", "role": "audience"}
        )

        await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "一条弹幕", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )

        # Get without auth
        r = await client.get(f"/api/rooms/{room['id']}/danmaku")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 1


# ── Like Tests ─────────────────────────────────────────────────────


class TestLikeRoom:
    @pytest.mark.asyncio
    async def test_like_success(self, client):
        """Audience can like a live room."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "liker", "role": "audience"}
        )

        r = await client.post(
            f"/api/rooms/{room['id']}/like",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["room_id"] == room["id"]
        assert body["data"]["total_likes"] == 1

    @pytest.mark.asyncio
    async def test_like_multiple_times(self, client):
        """Like incrementing works correctly."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "multiliker", "role": "audience"}
        )

        for i in range(5):
            r = await client.post(
                f"/api/rooms/{room['id']}/like",
                headers=_auth_headers(token),
            )
            assert r.status_code == 200
            assert r.json()["data"]["total_likes"] == i + 1

    @pytest.mark.asyncio
    async def test_like_unauthorized(self, client):
        """Unauthenticated users cannot like."""
        _, _, room = await _setup_live_room(client)

        r = await client.post(f"/api/rooms/{room['id']}/like")
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_like_limit(self, client):
        """Max 1000 likes per user per session."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "maxliker", "role": "audience"}
        )

        # Send 1000 likes (we'll test just the boundary)
        # Set the count to 999 first
        from app.core.redis import get_redis
        r = await get_redis()
        await r.set(f"room:{room['id']}:likes:{user_data['id']}", "999")

        # 1000th like should succeed
        resp = await client.post(
            f"/api/rooms/{room['id']}/like",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total_likes"] == 1000

        # 1001st should fail
        resp = await client.post(
            f"/api/rooms/{room['id']}/like",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 400
        assert "上限" in resp.json()["message"]


# ── Gift List Tests ────────────────────────────────────────────────


class TestGiftList:
    @pytest.mark.asyncio
    async def test_gift_list_empty(self, client):
        """Empty list when no gifts exist."""
        r = await client.get("/api/gifts")
        assert r.status_code == 200
        assert r.json()["code"] == 0
        assert r.json()["data"] == []

    @pytest.mark.asyncio
    async def test_gift_list_with_gifts(self, client):
        """Returns all active gifts."""
        await _seed_default_gifts()

        r = await client.get("/api/gifts")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert len(body["data"]) == 5

        names = [g["name"] for g in body["data"]]
        assert "小星星" in names
        assert "火箭" in names
        assert "守护船票" in names

        # Verify prices
        price_map = {g["name"]: g["price_fen"] for g in body["data"]}
        assert price_map["小星星"] == 100
        assert price_map["超级星舰"] == 50000

    @pytest.mark.asyncio
    async def test_gift_list_no_auth_required(self, client):
        """Gift list is public."""
        await _seed_default_gifts()
        r = await client.get("/api/gifts")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 5


# ── Send Gift Tests ────────────────────────────────────────────────


class TestSendGift:
    @pytest.mark.asyncio
    async def test_send_gift_success(self, client):
        """Audience can send a gift with sufficient balance."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "gifter", "role": "audience"}
        )
        await _seed_default_gifts()
        await _top_up_wallet(user_data["id"], 100000)  # 1000 yuan in fen

        r = await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 1, "quantity": 2},  # 小星星 x2 = 200 fen
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["gift_name"] == "小星星"
        assert body["data"]["quantity"] == 2
        assert body["data"]["total_amount_fen"] == 200
        assert body["data"]["balance_after_fen"] == 100000 - 200
        assert body["data"]["is_announcement"] is False

    @pytest.mark.asyncio
    async def test_send_gift_insufficient_balance(self, client):
        """Cannot send gift with insufficient balance (4001)."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "poorguy", "role": "audience"}
        )
        await _seed_default_gifts()
        await _top_up_wallet(user_data["id"], 50)  # Only 50 fen

        r = await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 1, "quantity": 1},  # 小星星 costs 100 fen
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 4001
        assert "余额不足" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_send_gift_not_found(self, client):
        """Nonexistent gift returns 4003."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "giftnotfound", "role": "audience"}
        )
        await _seed_default_gifts()
        await _top_up_wallet(user_data["id"], 100000)

        r = await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 99999, "quantity": 1},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 4003

    @pytest.mark.asyncio
    async def test_send_gift_announcement(self, client):
        """Diamond gifts trigger announcement flag."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "richguy", "role": "audience"}
        )
        await _seed_default_gifts()
        await _top_up_wallet(user_data["id"], 20000000)  # 200k yuan

        # Get gift IDs
        gift_list_r = await client.get("/api/gifts")
        gifts = {g["name"]: g["id"] for g in gift_list_r.json()["data"]}

        r = await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": gifts["超级星舰"], "quantity": 1},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_announcement"] is True

    @pytest.mark.asyncio
    async def test_send_gift_invalid_quantity(self, client):
        """Quantity must be 1-99."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "qtytester", "role": "audience"}
        )
        await _seed_default_gifts()
        await _top_up_wallet(user_data["id"], 100000)

        r = await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 1, "quantity": 100},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_send_gift_updates_consumption(self, client):
        """Sending a gift increases total_consumed_fen."""
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "consumer", "role": "audience"}
        )
        await _seed_default_gifts()
        await _top_up_wallet(user_data["id"], 100000)

        r = await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 1, "quantity": 5},  # 500 fen total
            headers=_auth_headers(token),
        )
        assert r.status_code == 200

        # Verify consumption updated
        from sqlalchemy import select
        from app.models.user import User
        async with test_session_factory() as session:
            result = await session.execute(
                select(User).where(User.id == user_data["id"])
            )
            u = result.scalar_one()
            assert u.total_consumed_fen == 500


# ── Gift Rank Tests ────────────────────────────────────────────────


class TestGiftRank:
    @pytest.mark.asyncio
    async def test_gift_rank_empty(self, client):
        """Empty rank when no gifts sent."""
        _, _, room = await _setup_live_room(client)
        await _seed_default_gifts()

        r = await client.get(f"/api/rooms/{room['id']}/gift-rank")
        assert r.status_code == 200
        assert r.json()["data"] == []

    @pytest.mark.asyncio
    async def test_gift_rank_with_senders(self, client):
        """Rank shows top senders."""
        _, _, room = await _setup_live_room(client)
        await _seed_default_gifts()

        # Create 3 audience users
        users = []
        for i in range(3):
            ud, tok = await _register_and_login(
                client, {"username": f"ranker{i}", "role": "audience"}
            )
            await _top_up_wallet(ud["id"], 1000000)
            users.append((ud, tok))

        # User 0 sends 小星星 x1 (100 fen)
        await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 1, "quantity": 1},
            headers=_auth_headers(users[0][1]),
        )
        # User 1 sends 小星星 x10 (1000 fen)
        await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 1, "quantity": 10},
            headers=_auth_headers(users[1][1]),
        )
        # User 2 sends 爱心 x3 (1500 fen)
        await client.post(
            f"/api/rooms/{room['id']}/gifts",
            json={"gift_id": 2, "quantity": 3},
            headers=_auth_headers(users[2][1]),
        )

        r = await client.get(f"/api/rooms/{room['id']}/gift-rank")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 3
        # Sorted by total_amount_fen descending
        assert data[0]["total_amount_fen"] == 1500
        assert data[0]["rank"] == 1
        assert data[1]["total_amount_fen"] == 1000
        assert data[1]["rank"] == 2
        assert data[2]["total_amount_fen"] == 100
        assert data[2]["rank"] == 3


# ── Forbidden Words Tests (admin) ──────────────────────────────────


class TestForbiddenWords:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        """Admin can list empty forbidden words."""
        _, admin_token = await _create_admin(client)

        r = await client.get(
            "/api/admin/forbidden-words", headers=_auth_headers(admin_token)
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    @pytest.mark.asyncio
    async def test_list_non_admin(self, client):
        """Non-admin cannot list forbidden words."""
        user_data, token = await _register_and_login(
            client, {"username": "notadmin", "role": "audience"}
        )

        r = await client.get(
            "/api/admin/forbidden-words", headers=_auth_headers(token)
        )
        assert r.status_code == 403
        assert r.json()["code"] == 1003

    @pytest.mark.asyncio
    async def test_create_forbidden_word(self, client):
        """Admin can add a forbidden word."""
        _, admin_token = await _create_admin(client)

        r = await client.post(
            "/api/admin/forbidden-words",
            json={"word": "违禁测试"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["word"] == "违禁测试"
        assert body["data"]["id"] is not None
        datetime.fromisoformat(body["data"]["created_at"])

    @pytest.mark.asyncio
    async def test_create_duplicate(self, client):
        """Cannot add duplicate forbidden word."""
        _, admin_token = await _create_admin(client)

        await client.post(
            "/api/admin/forbidden-words",
            json={"word": "重复词"},
            headers=_auth_headers(admin_token),
        )
        r = await client.post(
            "/api/admin/forbidden-words",
            json={"word": "重复词"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001
        assert "已存在" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_delete_forbidden_word(self, client):
        """Admin can delete a forbidden word."""
        _, admin_token = await _create_admin(client)

        # Create one
        r = await client.post(
            "/api/admin/forbidden-words",
            json={"word": "待删除"},
            headers=_auth_headers(admin_token),
        )
        word_id = r.json()["data"]["id"]

        # Delete
        r = await client.delete(
            f"/api/admin/forbidden-words/{word_id}",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0
        assert "删除" in r.json()["message"]

        # Verify it's gone from list
        r = await client.get(
            "/api/admin/forbidden-words", headers=_auth_headers(admin_token)
        )
        assert len(r.json()["data"]) == 0

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client):
        """Delete nonexistent word returns 404."""
        _, admin_token = await _create_admin(client)

        r = await client.delete(
            "/api/admin/forbidden-words/99999",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 404
        assert r.json()["code"] == 1004

    @pytest.mark.asyncio
    async def test_forbidden_word_blocks_danmaku(self, client):
        """Adding a forbidden word via API blocks danmaku."""
        _, admin_token = await _create_admin(client)
        _, _, room = await _setup_live_room(client)
        user_data, token = await _register_and_login(
            client, {"username": "filtertester", "role": "audience"}
        )

        # Add forbidden word via admin API
        await client.post(
            "/api/admin/forbidden-words",
            json={"word": "违规"},
            headers=_auth_headers(admin_token),
        )

        # Try to send danmaku with forbidden word
        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "这是违规内容", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert "违禁词" in r.json()["message"]

        # Danmaku without forbidden word still works
        r = await client.post(
            f"/api/rooms/{room['id']}/danmaku",
            json={"content": "正常内容", "color": "#FFFFFF"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
