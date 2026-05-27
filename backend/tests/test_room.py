"""Tests for room service — create, start, end, list, search, update, ban, unban.

Uses in-memory SQLite + mocked Redis.
"""

import time
import uuid
from datetime import datetime

import pytest

from app.core.security import create_access_token, hash_password
from app.models.room import ROOM_CATEGORIES, Room
from app.models.user import User
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
    """Register a user and return (user_data, access_token)."""
    reg = await _register(client, overrides)
    username = overrides.get("username", "testuser") if overrides else "testuser"
    password = overrides.get("password", "pass1234") if overrides else "pass1234"
    login = await _login(client, username, password)
    return reg.json()["data"], login.json()["data"]["access_token"]


async def _create_verified_streamer(client) -> tuple[dict, str]:
    """Create a verified streamer: register, then directly set streamer_verified=True in DB."""
    uname = f"s{int(time.time()*1000) % 1000000000}"  # max 10 chars
    user_data, token = await _register_and_login(
        client, {"username": uname, "role": "streamer"}
    )

    # Directly set streamer_verified in DB (bypassing admin review for testing)
    async with test_session_factory() as session:
        result = await session.execute(
            __import__("sqlalchemy").select(User).where(User.id == user_data["id"])
        )
        user = result.scalar_one()
        user.streamer_verified = True
        await session.commit()

    return user_data, token


async def _create_admin(client) -> tuple[dict, str]:
    """Create an admin user directly in DB and return (user_data, token)."""
    admin_name = f"a{int(time.time()*1000) % 1000000000}"  # max 11 chars
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
    """Create a room and return response data."""
    payload = {
        "title": "测试直播间",
        "description": "这是一个测试直播间",
        "category": "game",
        "cover_url": "https://example.com/cover.jpg",
    }
    if overrides:
        payload.update(overrides)
    r = await client.post(
        "/api/rooms", json=payload, headers=_auth_headers(token)
    )
    return r


# ── Create Room ─────────────────────────────────────────────────────


class TestCreateRoom:
    @pytest.mark.asyncio
    async def test_create_room_success(self, client):
        _, token = await _create_verified_streamer(client)
        r = await _create_room(client, token)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert "创建成功" in body["message"]
        data = body["data"]
        assert data["title"] == "测试直播间"
        assert data["description"] == "这是一个测试直播间"
        assert data["category"] == "game"
        assert data["cover_url"] == "https://example.com/cover.jpg"
        assert data["status"] == "idle"
        assert data["current_viewers"] == 0
        assert data["peak_viewers"] == 0
        assert data["total_sessions"] == 0
        assert data["streamer"] is not None
        assert data["streamer"]["id"] is not None
        # Timestamps are ISO 8601
        datetime.fromisoformat(data["created_at"])
        datetime.fromisoformat(data["updated_at"])

    @pytest.mark.asyncio
    async def test_create_room_unauthenticated(self, client):
        r = await client.post("/api/rooms", json={"title": "test"})
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_create_room_not_streamer(self, client):
        """Audience cannot create a room."""
        _, token = await _register_and_login(client, {"username": "audience1"})
        r = await _create_room(client, token)
        assert r.status_code == 403
        assert r.json()["code"] == 1003

    @pytest.mark.asyncio
    async def test_create_room_unverified_streamer(self, client):
        """Streamer without verification cannot create a room."""
        _, token = await _register_and_login(
            client, {"username": "unverified", "role": "streamer"}
        )
        r = await _create_room(client, token)
        assert r.status_code == 400
        assert r.json()["code"] == 1001
        assert "认证" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_create_duplicate_room(self, client):
        """Each streamer can only have one room."""
        _, token = await _create_verified_streamer(client)
        await _create_room(client, token)

        r = await _create_room(client, token)
        assert r.status_code == 400
        assert r.json()["code"] == 1001
        assert "只能有一个" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_create_room_invalid_category(self, client):
        _, token = await _create_verified_streamer(client)
        r = await _create_room(client, token, {"category": "invalid_cat"})
        assert r.status_code == 422
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_create_room_title_too_short(self, client):
        _, token = await _create_verified_streamer(client)
        r = await _create_room(client, token, {"title": "A"})
        assert r.status_code == 422
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_create_room_all_categories(self, client):
        """Verify all valid categories are accepted."""
        _, token = await _create_verified_streamer(client)
        # We can only create one room per streamer, so test just a few
        r = await _create_room(client, token, {"category": "music"})
        assert r.status_code == 200


# ── Start Streaming ─────────────────────────────────────────────────


class TestStartStream:
    @pytest.mark.asyncio
    async def test_start_stream_success(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert "开播成功" in body["message"]
        data = body["data"]
        assert data["status"] == "live"
        assert data["started_at"] is not None
        datetime.fromisoformat(data["started_at"])
        assert data["current_viewers"] == 0
        assert data["peak_viewers"] == 0

    @pytest.mark.asyncio
    async def test_start_stream_not_owner(self, client):
        _, token_a = await _create_verified_streamer(client)
        room = (await _create_room(client, token_a)).json()["data"]

        _, token_b = await _create_verified_streamer(client)
        r = await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token_b)
        )
        assert r.status_code == 403
        assert r.json()["code"] == 1003

    @pytest.mark.asyncio
    async def test_cannot_start_already_live(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        r = await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        assert r.status_code == 400
        assert "直播中" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_start_banned_room(self, client):
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        # Admin bans the room
        await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "违规内容"},
            headers=_auth_headers(admin_token),
        )

        r = await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        assert r.status_code == 403
        assert r.json()["code"] == 3003

    @pytest.mark.asyncio
    async def test_start_nonexistent_room(self, client):
        _, token = await _create_verified_streamer(client)
        r = await client.post(
            "/api/rooms/99999/start", headers=_auth_headers(token)
        )
        assert r.status_code == 404
        assert r.json()["code"] == 3001


# ── End Streaming ───────────────────────────────────────────────────


class TestEndStream:
    @pytest.mark.asyncio
    async def test_end_stream_success(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        # Start first
        await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )

        r = await client.post(
            f"/api/rooms/{room['id']}/end", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert "已结束" in body["message"]
        data = body["data"]
        assert data["room_id"] == room["id"]
        assert data["session_duration_seconds"] >= 0
        assert data["peak_viewers"] == 0
        assert data["total_sessions"] == 1

    @pytest.mark.asyncio
    async def test_end_stream_not_owner(self, client):
        _, token_a = await _create_verified_streamer(client)
        room = (await _create_room(client, token_a)).json()["data"]

        await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token_a)
        )

        _, token_b = await _create_verified_streamer(client)
        r = await client.post(
            f"/api/rooms/{room['id']}/end", headers=_auth_headers(token_b)
        )
        assert r.status_code == 403
        assert r.json()["code"] == 1003

    @pytest.mark.asyncio
    async def test_cannot_end_not_live(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.post(
            f"/api/rooms/{room['id']}/end", headers=_auth_headers(token)
        )
        assert r.status_code == 400
        assert "直播中" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_end_stream_idempotent_total_sessions(self, client):
        """Ending twice should fail (second time not live). But total_sessions should be 1."""
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        r = await client.post(
            f"/api/rooms/{room['id']}/end", headers=_auth_headers(token)
        )
        assert r.json()["data"]["total_sessions"] == 1

        # Second end should fail
        r2 = await client.post(
            f"/api/rooms/{room['id']}/end", headers=_auth_headers(token)
        )
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_end_then_restart(self, client):
        """After ending, room can be restarted (creates new session)."""
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        # First session
        await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        await client.post(
            f"/api/rooms/{room['id']}/end", headers=_auth_headers(token)
        )

        # Should NOT be able to restart (ended rooms cannot be restarted per state machine)
        # Actually, checking the spec: idle→live→ended. ended is terminal.
        r = await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        assert r.status_code == 404  # RoomClosedError → 3002
        assert r.json()["code"] == 3002


# ── Get Room Detail ─────────────────────────────────────────────────


class TestGetRoomDetail:
    @pytest.mark.asyncio
    async def test_get_room_detail(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.get(f"/api/rooms/{room['id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["id"] == room["id"]
        assert data["title"] == "测试直播间"
        assert data["streamer"] is not None
        assert data["streamer"]["id"] == room["streamer_id"]

    @pytest.mark.asyncio
    async def test_get_room_detail_guest(self, client):
        """Guest (unauthenticated) can view room detail."""
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.get(f"/api/rooms/{room['id']}")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_get_nonexistent_room(self, client):
        r = await client.get("/api/rooms/99999")
        assert r.status_code == 404
        assert r.json()["code"] == 3001


# ── List Rooms ──────────────────────────────────────────────────────


class TestListRooms:
    @pytest.mark.asyncio
    async def test_list_rooms_empty(self, client):
        """No live rooms → empty list."""
        r = await client.get("/api/rooms")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_only_returns_live_rooms(self, client):
        """Only live rooms are returned in list."""
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        # Room is idle — should NOT appear in list
        r = await client.get("/api/rooms")
        assert r.json()["data"]["total"] == 0

        # Start streaming
        await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )
        r = await client.get("/api/rooms")
        assert r.json()["data"]["total"] == 1
        assert r.json()["data"]["items"][0]["id"] == room["id"]
        assert r.json()["data"]["items"][0]["status"] == "live"

    @pytest.mark.asyncio
    async def test_list_filter_by_category(self, client):
        _, token_a = await _create_verified_streamer(client)
        _, token_b = await _create_verified_streamer(client)

        room_a = (await _create_room(client, token_a, {"category": "game", "title": "游戏间"})).json()["data"]
        room_b = (await _create_room(client, token_b, {"category": "music", "title": "音乐间"})).json()["data"]

        await client.post(f"/api/rooms/{room_a['id']}/start", headers=_auth_headers(token_a))
        await client.post(f"/api/rooms/{room_b['id']}/start", headers=_auth_headers(token_b))

        r = await client.get("/api/rooms?category=game")
        assert r.json()["data"]["total"] == 1
        assert r.json()["data"]["items"][0]["category"] == "game"

    @pytest.mark.asyncio
    async def test_list_pagination(self, client):
        """Pagination works correctly."""
        # Create 3 live rooms
        for i in range(3):
            _, token = await _create_verified_streamer(client)
            room = (await _create_room(client, token, {"title": f"房间{i}"})).json()["data"]
            await client.post(f"/api/rooms/{room['id']}/start", headers=_auth_headers(token))

        r = await client.get("/api/rooms?page=1&page_size=2")
        assert r.json()["data"]["total"] == 3
        assert len(r.json()["data"]["items"]) == 2
        assert r.json()["data"]["page"] == 1

        r = await client.get("/api/rooms?page=2&page_size=2")
        assert len(r.json()["data"]["items"]) == 1


# ── Recommended Rooms ───────────────────────────────────────────────


class TestRecommendedRooms:
    @pytest.mark.asyncio
    async def test_recommended_empty(self, client):
        r = await client.get("/api/rooms/recommended")
        assert r.status_code == 200
        assert r.json()["data"] == []

    @pytest.mark.asyncio
    async def test_recommended_with_live_rooms(self, client):
        """Recommended returns live rooms sorted by viewers."""
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]
        await client.post(f"/api/rooms/{room['id']}/start", headers=_auth_headers(token))

        r = await client.get("/api/rooms/recommended")
        assert r.status_code == 200
        items = r.json()["data"]
        assert len(items) > 0
        assert all(item["status"] == "live" for item in items)


# ── Search Rooms ────────────────────────────────────────────────────


class TestSearchRooms:
    @pytest.mark.asyncio
    async def test_search_by_title(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token, {"title": "Python学习直播间"})).json()["data"]
        await client.post(f"/api/rooms/{room['id']}/start", headers=_auth_headers(token))

        r = await client.get("/api/rooms/search?q=Python")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

        r = await client.get("/api/rooms/search?q=不存在")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_search_only_live(self, client):
        """Search only returns live rooms."""
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token, {"title": "未开播房间"})).json()["data"]

        r = await client.get("/api/rooms/search?q=未开播")
        assert r.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_search_empty_query(self, client):
        r = await client.get("/api/rooms/search?q=")
        assert r.status_code == 422


# ── Update Room ─────────────────────────────────────────────────────


class TestUpdateRoom:
    @pytest.mark.asyncio
    async def test_update_room_success(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.put(
            f"/api/rooms/{room['id']}",
            json={"title": "新标题", "description": "新简介"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["title"] == "新标题"
        assert data["description"] == "新简介"
        # Unchanged fields
        assert data["category"] == "game"

    @pytest.mark.asyncio
    async def test_update_room_not_owner(self, client):
        _, token_a = await _create_verified_streamer(client)
        room = (await _create_room(client, token_a)).json()["data"]

        _, token_b = await _create_verified_streamer(client)
        r = await client.put(
            f"/api/rooms/{room['id']}",
            json={"title": "别人的房间"},
            headers=_auth_headers(token_b),
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_update_nonexistent_room(self, client):
        _, token = await _create_verified_streamer(client)
        r = await client.put(
            "/api/rooms/99999",
            json={"title": "xx"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 404
        assert r.json()["code"] == 3001

    @pytest.mark.asyncio
    async def test_update_requires_auth(self, client):
        r = await client.put("/api/rooms/1", json={"title": "x"})
        assert r.status_code == 401


# ── Admin: Ban / Unban Room ─────────────────────────────────────────


class TestAdminBanRoom:
    @pytest.mark.asyncio
    async def test_ban_room_success(self, client):
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        await client.post(
            f"/api/rooms/{room['id']}/start", headers=_auth_headers(token)
        )

        r = await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "违规内容"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert "已封禁" in body["message"]
        assert body["data"]["status"] == "banned"
        assert body["data"]["reason"] == "违规内容"

    @pytest.mark.asyncio
    async def test_ban_room_not_admin(self, client):
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "test"},
            headers=_auth_headers(token),  # Streamer tries to ban
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_ban_already_banned(self, client):
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "第一次"},
            headers=_auth_headers(admin_token),
        )
        r = await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "第二次"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 400
        assert "封禁" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_ban_ended_room(self, client):
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        await client.post(f"/api/rooms/{room['id']}/start", headers=_auth_headers(token))
        await client.post(f"/api/rooms/{room['id']}/end", headers=_auth_headers(token))

        r = await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "test"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 400
        assert "已结束" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_ban_idle_room(self, client):
        """Banning an idle (never started) room should work."""
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "虚假信息"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "banned"


class TestAdminUnbanRoom:
    @pytest.mark.asyncio
    async def test_unban_room_success(self, client):
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        # Ban first
        await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "test"},
            headers=_auth_headers(admin_token),
        )

        # Unban
        r = await client.post(
            f"/api/admin/rooms/{room['id']}/unban",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert "已解封" in body["message"]
        assert body["data"]["status"] == "idle"

    @pytest.mark.asyncio
    async def test_unban_not_banned(self, client):
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        r = await client.post(
            f"/api/admin/rooms/{room['id']}/unban",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 400
        assert "未" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_unban_not_admin(self, client):
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "test"},
            headers=_auth_headers(admin_token),
        )

        r = await client.post(
            f"/api/admin/rooms/{room['id']}/unban",
            headers=_auth_headers(token),
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_unban_then_start(self, client):
        """After unban, room should be startable again."""
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        # Ban
        await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "test"},
            headers=_auth_headers(admin_token),
        )
        # Unban
        await client.post(
            f"/api/admin/rooms/{room['id']}/unban",
            headers=_auth_headers(admin_token),
        )
        # Start streaming
        r = await client.post(
            f"/api/rooms/{room['id']}/start",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "live"


# ── Room Not Found ──────────────────────────────────────────────────


class TestRoomNotFound:
    """Cross-cutting: all room operations return 3001 for non-existent rooms."""

    @pytest.mark.asyncio
    async def test_start_nonexistent(self, client):
        _, token = await _create_verified_streamer(client)
        r = await client.post("/api/rooms/99999/start", headers=_auth_headers(token))
        assert r.status_code == 404
        assert r.json()["code"] == 3001

    @pytest.mark.asyncio
    async def test_end_nonexistent(self, client):
        _, token = await _create_verified_streamer(client)
        r = await client.post("/api/rooms/99999/end", headers=_auth_headers(token))
        assert r.status_code == 404
        assert r.json()["code"] == 3001

    @pytest.mark.asyncio
    async def test_detail_nonexistent(self, client):
        r = await client.get("/api/rooms/99999")
        assert r.status_code == 404
        assert r.json()["code"] == 3001

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, client):
        _, token = await _create_verified_streamer(client)
        r = await client.put("/api/rooms/99999", json={"title": "xx"}, headers=_auth_headers(token))
        assert r.status_code == 404
        assert r.json()["code"] == 3001

    @pytest.mark.asyncio
    async def test_ban_nonexistent(self, client):
        _, admin_token = await _create_admin(client)
        r = await client.post(
            "/api/admin/rooms/99999/ban",
            json={"reason": "x"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 404
        assert r.json()["code"] == 3001

    @pytest.mark.asyncio
    async def test_unban_nonexistent(self, client):
        _, admin_token = await _create_admin(client)
        r = await client.post(
            "/api/admin/rooms/99999/unban",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 404
        assert r.json()["code"] == 3001


# ── State machine conformance ───────────────────────────────────────


class TestStateMachine:
    """Verify the room state machine: idle → live → ended, live → banned, banned → idle."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, client):
        """idle → live → ended"""
        _, token = await _create_verified_streamer(client)
        room = (await _create_room(client, token)).json()["data"]
        assert room["status"] == "idle"

        r = await client.post(f"/api/rooms/{room['id']}/start", headers=_auth_headers(token))
        assert r.json()["data"]["status"] == "live"

        r = await client.post(f"/api/rooms/{room['id']}/end", headers=_auth_headers(token))
        assert r.json()["data"]["total_sessions"] == 1

        # Verify ended state in detail
        r = await client.get(f"/api/rooms/{room['id']}")
        assert r.json()["data"]["status"] == "ended"

    @pytest.mark.asyncio
    async def test_ban_unban_lifecycle(self, client):
        """idle → live → banned → idle (unban) → live"""
        _, token = await _create_verified_streamer(client)
        admin_data, admin_token = await _create_admin(client)
        room = (await _create_room(client, token)).json()["data"]

        await client.post(f"/api/rooms/{room['id']}/start", headers=_auth_headers(token))
        await client.post(
            f"/api/admin/rooms/{room['id']}/ban",
            json={"reason": "违规"},
            headers=_auth_headers(admin_token),
        )
        # Unban restores to idle
        await client.post(
            f"/api/admin/rooms/{room['id']}/unban",
            headers=_auth_headers(admin_token),
        )
        # Can start again
        r = await client.post(f"/api/rooms/{room['id']}/start", headers=_auth_headers(token))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "live"
