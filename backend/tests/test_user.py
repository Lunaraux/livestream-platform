"""Tests for user service — profile, follow, password, ban, streamer verify.

Uses in-memory SQLite + mocked Redis.
"""

import time
from datetime import datetime

import pytest

from app.core.security import hash_password
from app.models.user import StreamerApplication, User


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
    """Register a user and return (response_data, access_token)."""
    reg = await _register(client, overrides)
    username = overrides.get("username", "testuser") if overrides else "testuser"
    password = overrides.get("password", "pass1234") if overrides else "pass1234"
    login = await _login(client, username, password)
    return reg.json()["data"], login.json()["data"]["access_token"]


async def _create_admin(client) -> tuple[dict, str]:
    """Create an admin user directly in DB and return (user_data, token)."""
    import uuid

    from app.core.security import create_access_token
    from tests.conftest import test_session_factory

    admin_name = f"admin_{int(time.time()*1000)}"
    password = "admin1234"

    async with test_session_factory() as session:
        now = int(time.time())
        admin = User(
            username=admin_name,
            password_hash=hash_password(password),
            nickname="管理员",
            role="admin",
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        admin_id = admin.id
        access_token, _ = create_access_token(
            {"sub": str(admin_id), "jti": str(uuid.uuid4())}
        )
        return {"id": admin_id, "username": admin_name}, access_token


# ── User Profile ───────────────────────────────────────────────────


class TestGetUserProfile:
    @pytest.mark.asyncio
    async def test_guest_views_profile(self, client):
        """Guest can view a user's public profile."""
        user_data, _ = await _register_and_login(client)
        user_id = user_data["id"]

        r = await client.get(f"/api/users/{user_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["username"] == "testuser"
        assert data["nickname"] == "测试用户"
        assert data["role"] == "audience"
        assert data["level"] == 1
        assert data["follower_count"] == 0
        assert data["following_count"] == 0
        assert data["is_following"] is False
        assert data["level_name"] == "普通观众"

    @pytest.mark.asyncio
    async def test_authenticated_views_other_profile(self, client):
        """Authenticated user viewing someone not followed."""
        _, token_a = await _register_and_login(client, {"username": "usera"})
        user_b, _ = await _register_and_login(client, {"username": "userb"})

        r = await client.get(
            f"/api/users/{user_b['id']}", headers=_auth_headers(token_a)
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_following"] is False

    @pytest.mark.asyncio
    async def test_authenticated_views_followed_streamer(self, client):
        """Viewing a streamer you follow shows is_following=true."""
        _, token_a = await _register_and_login(client, {"username": "user_a"})
        streamer, token_s = await _register_and_login(
            client, {"username": "streamer_x", "role": "streamer"}
        )

        # Follow the streamer
        r = await client.post(
            f"/api/users/{streamer['id']}/follow", headers=_auth_headers(token_a)
        )
        assert r.status_code == 200

        # View as follower
        r = await client.get(
            f"/api/users/{streamer['id']}", headers=_auth_headers(token_a)
        )
        assert r.json()["data"]["is_following"] is True

    @pytest.mark.asyncio
    async def test_nonexistent_user(self, client):
        r = await client.get("/api/users/99999")
        assert r.status_code == 404
        assert r.json()["code"] == 1004


# ── Update Profile ─────────────────────────────────────────────────


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_nickname(self, client):
        user_data, token = await _register_and_login(client)

        r = await client.put(
            "/api/users/me",
            json={"nickname": "新昵称"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0
        assert r.json()["data"]["nickname"] == "新昵称"

    @pytest.mark.asyncio
    async def test_update_avatar(self, client):
        _, token = await _register_and_login(client)

        r = await client.put(
            "/api/users/me",
            json={"avatar_url": "https://example.com/avatar.png"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["avatar_url"] == "https://example.com/avatar.png"

    @pytest.mark.asyncio
    async def test_update_bio(self, client):
        _, token = await _register_and_login(client)

        r = await client.put(
            "/api/users/me",
            json={"bio": "这是我的简介"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["bio"] == "这是我的简介"

    @pytest.mark.asyncio
    async def test_update_all_fields(self, client):
        _, token = await _register_and_login(client)

        r = await client.put(
            "/api/users/me",
            json={
                "nickname": "全新华名",
                "avatar_url": "https://img.com/pic.jpg",
                "bio": "新简介内容",
            },
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["nickname"] == "全新华名"
        assert data["avatar_url"] == "https://img.com/pic.jpg"
        assert data["bio"] == "新简介内容"

    @pytest.mark.asyncio
    async def test_partial_update_only_nickname(self, client):
        """Only nickname provided — other fields unchanged."""
        _, token = await _register_and_login(client)

        # Set bio first
        await client.put(
            "/api/users/me",
            json={"bio": "原始简介"},
            headers=_auth_headers(token),
        )

        # Update only nickname
        r = await client.put(
            "/api/users/me",
            json={"nickname": "仅改昵称"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["nickname"] == "仅改昵称"
        assert data["bio"] == "原始简介"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_requires_auth(self, client):
        r = await client.put("/api/users/me", json={"nickname": "x"})
        assert r.status_code == 401
        assert r.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_nickname_too_short(self, client):
        _, token = await _register_and_login(client)
        r = await client.put(
            "/api/users/me",
            json={"nickname": "A"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001


# ── Change Password ────────────────────────────────────────────────


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_success(self, client):
        user_data, token = await _register_and_login(client)

        r = await client.post(
            "/api/users/me/password",
            json={"old_password": "pass1234", "new_password": "newpass9"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0
        assert "密码修改成功" in r.json()["message"]

        # Can login with new password
        r = await _login(client, password="newpass9")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_old(self, client):
        _, token = await _register_and_login(client)

        r = await client.post(
            "/api/users/me/password",
            json={"old_password": "wrongold", "new_password": "newpass9"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 2002

    @pytest.mark.asyncio
    async def test_change_password_same_as_old(self, client):
        _, token = await _register_and_login(client)

        r = await client.post(
            "/api/users/me/password",
            json={"old_password": "pass1234", "new_password": "pass1234"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_change_password_requires_auth(self, client):
        r = await client.post(
            "/api/users/me/password",
            json={"old_password": "x", "new_password": "newpass9"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_new_password_no_digit(self, client):
        _, token = await _register_and_login(client)
        r = await client.post(
            "/api/users/me/password",
            json={"old_password": "pass1234", "new_password": "abcdefgh"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001

    @pytest.mark.asyncio
    async def test_new_password_no_letter(self, client):
        _, token = await _register_and_login(client)
        r = await client.post(
            "/api/users/me/password",
            json={"old_password": "pass1234", "new_password": "12345678"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == 1001


# ── Follow / Unfollow ──────────────────────────────────────────────


class TestFollow:
    @pytest.mark.asyncio
    async def test_follow_streamer_success(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})
        streamer, _ = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        r = await client.post(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_following"] is True
        assert "关注成功" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_follow_self(self, client):
        user_data, token = await _register_and_login(client)

        r = await client.post(
            f"/api/users/{user_data['id']}/follow",
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert "不能关注自己" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_follow_non_streamer(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})
        user_b, _ = await _register_and_login(client, {"username": "userb"})

        r = await client.post(
            f"/api/users/{user_b['id']}/follow",
            headers=_auth_headers(token_a),
        )
        assert r.status_code == 400
        assert "不是主播" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_follow_twice(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})
        streamer, _ = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        await client.post(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )
        r = await client.post(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )
        assert r.status_code == 400
        assert "已关注" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_follow_nonexistent(self, client):
        _, token = await _register_and_login(client)

        r = await client.post(
            "/api/users/99999/follow", headers=_auth_headers(token)
        )
        assert r.status_code == 404
        assert r.json()["code"] == 1004


class TestUnfollow:
    @pytest.mark.asyncio
    async def test_unfollow_success(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})
        streamer, _ = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        # Follow first
        await client.post(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )

        # Unfollow
        r = await client.delete(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_following"] is False
        assert "取消关注" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_unfollow_if_not_following(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})
        streamer, _ = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        r = await client.delete(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )
        assert r.status_code == 400
        assert "未关注" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_unfollow_update_reflected_in_profile(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})
        streamer, _ = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        # Follow
        await client.post(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )
        # Verify is_following
        r = await client.get(
            f"/api/users/{streamer['id']}", headers=_auth_headers(token_a)
        )
        assert r.json()["data"]["is_following"] is True

        # Unfollow
        await client.delete(
            f"/api/users/{streamer['id']}/follow",
            headers=_auth_headers(token_a),
        )
        # Verify is_following is false
        r = await client.get(
            f"/api/users/{streamer['id']}", headers=_auth_headers(token_a)
        )
        assert r.json()["data"]["is_following"] is False

    @pytest.mark.asyncio
    async def test_unfollow_requires_auth(self, client):
        r = await client.delete("/api/users/1/follow")
        assert r.status_code == 401


# ── Following List ─────────────────────────────────────────────────


class TestFollowingList:
    @pytest.mark.asyncio
    async def test_get_following_empty(self, client):
        _, token = await _register_and_login(client)

        r = await client.get(
            "/api/users/me/following", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_following_with_follows(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})
        s1, _ = await _register_and_login(
            client, {"username": "streamer_a", "role": "streamer"}
        )
        s2, _ = await _register_and_login(
            client, {"username": "streamer_b", "role": "streamer"}
        )

        # Follow both
        await client.post(
            f"/api/users/{s1['id']}/follow", headers=_auth_headers(token_a)
        )
        await client.post(
            f"/api/users/{s2['id']}/follow", headers=_auth_headers(token_a)
        )

        r = await client.get(
            "/api/users/me/following", headers=_auth_headers(token_a)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_following_requires_auth(self, client):
        r = await client.get("/api/users/me/following")
        assert r.status_code == 401


# ── Followers List ─────────────────────────────────────────────────


class TestFollowersList:
    @pytest.mark.asyncio
    async def test_streamer_sees_followers(self, client):
        streamer, token_s = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )
        _, token_a = await _register_and_login(client, {"username": "fan1"})

        # Fan follows streamer
        await client.post(
            f"/api/users/{streamer['id']}/follow", headers=_auth_headers(token_a)
        )

        r = await client.get(
            "/api/users/me/followers", headers=_auth_headers(token_s)
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["username"] == "fan1"

    @pytest.mark.asyncio
    async def test_audience_cannot_see_followers(self, client):
        _, token_a = await _register_and_login(client, {"username": "usera"})

        r = await client.get(
            "/api/users/me/followers", headers=_auth_headers(token_a)
        )
        assert r.status_code == 403
        assert r.json()["code"] == 1003

    @pytest.mark.asyncio
    async def test_empty_followers(self, client):
        streamer, token_s = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        r = await client.get(
            "/api/users/me/followers", headers=_auth_headers(token_s)
        )
        assert r.status_code == 200
        assert r.json()["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_followers_requires_auth(self, client):
        r = await client.get("/api/users/me/followers")
        assert r.status_code == 401


# ── Apply Streamer ─────────────────────────────────────────────────


class TestApplyStreamer:
    @pytest.mark.asyncio
    async def test_apply_success(self, client):
        streamer, token = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        r = await client.post(
            "/api/users/me/apply-streamer",
            json={"real_name": "张三", "id_number": "320102199001011234"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0
        data = r.json()["data"]
        assert data["real_name"] == "张三"
        # ID number should be masked
        assert "*" in data["id_number"]
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_audience_cannot_apply(self, client):
        _, token = await _register_and_login(client)

        r = await client.post(
            "/api/users/me/apply-streamer",
            json={"real_name": "张三", "id_number": "320102199001011234"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert "不是主播" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_cannot_apply_twice(self, client):
        _, token = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        await client.post(
            "/api/users/me/apply-streamer",
            json={"real_name": "张三", "id_number": "320102199001011234"},
            headers=_auth_headers(token),
        )
        r = await client.post(
            "/api/users/me/apply-streamer",
            json={"real_name": "张三", "id_number": "320102199001011234"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 400
        assert "已提交过" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_apply_with_short_id_number(self, client):
        _, token = await _register_and_login(
            client, {"username": "streamer1", "role": "streamer"}
        )

        r = await client.post(
            "/api/users/me/apply-streamer",
            json={"real_name": "张三", "id_number": "123"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 422


# ── Admin: Ban / Unban ─────────────────────────────────────────────


class TestBanUnban:
    async def _get_admin_token(self, client) -> str:
        """Get an admin token, creating an admin user if needed."""
        admin_data, admin_token = await _create_admin(client)
        return admin_token

    @pytest.mark.asyncio
    async def test_admin_ban_user(self, client):
        admin_token = await self._get_admin_token(client)
        user_data, _ = await _register_and_login(client, {"username": "victim"})

        r = await client.post(
            f"/api/admin/users/{user_data['id']}/ban",
            json={"reason": "违规发言", "duration_hours": 24},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0
        data = r.json()["data"]
        assert data["is_banned"] is True
        assert data["ban_reason"] == "违规发言"

    @pytest.mark.asyncio
    async def test_admin_permanent_ban(self, client):
        admin_token = await self._get_admin_token(client)
        user_data, _ = await _register_and_login(client, {"username": "victim2"})

        r = await client.post(
            f"/api/admin/users/{user_data['id']}/ban",
            json={"reason": "严重违规", "duration_hours": 0},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_banned"] is True

    @pytest.mark.asyncio
    async def test_admin_unban_user(self, client):
        admin_token = await self._get_admin_token(client)
        user_data, _ = await _register_and_login(client, {"username": "victim3"})

        # Ban first
        await client.post(
            f"/api/admin/users/{user_data['id']}/ban",
            json={"reason": "违规", "duration_hours": 24},
            headers=_auth_headers(admin_token),
        )

        # Unban
        r = await client.post(
            f"/api/admin/users/{user_data['id']}/unban",
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["is_banned"] is False

    @pytest.mark.asyncio
    async def test_cannot_ban_admin(self, client):
        admin_token = await self._get_admin_token(client)
        admin2_data, _ = await _create_admin(client)

        r = await client.post(
            f"/api/admin/users/{admin2_data['id']}/ban",
            json={"reason": "test", "duration_hours": 1},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_ban(self, client):
        _, token = await _register_and_login(client)

        r = await client.post(
            "/api/admin/users/1/ban",
            json={"reason": "test", "duration_hours": 1},
            headers=_auth_headers(token),
        )
        assert r.status_code == 403
        assert r.json()["code"] == 1003

    @pytest.mark.asyncio
    async def test_banned_user_cannot_use_token(self, client):
        """Banned users can still login but cannot use authenticated endpoints."""
        admin_token = await self._get_admin_token(client)
        user_data, user_token = await _register_and_login(
            client, {"username": "banned_user"}
        )

        # Ban
        await client.post(
            f"/api/admin/users/{user_data['id']}/ban",
            json={"reason": "违规", "duration_hours": 24},
            headers=_auth_headers(admin_token),
        )

        # Can still login to get tokens
        r = await _login(client, username="banned_user", password="pass1234")
        assert r.status_code == 200
        new_token = r.json()["data"]["access_token"]

        # But cannot use the token on authenticated endpoints
        r = await client.get(
            "/api/users/me/following", headers=_auth_headers(new_token)
        )
        assert r.status_code == 403
        assert r.json()["code"] == 2003

    @pytest.mark.asyncio
    async def test_ban_nonexistent_user(self, client):
        admin_token = await self._get_admin_token(client)

        r = await client.post(
            "/api/admin/users/99999/ban",
            json={"reason": "test", "duration_hours": 1},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 404


# ── Admin: Streamer Verify ─────────────────────────────────────────


class TestStreamerVerify:
    async def _get_admin_token(self, client) -> str:
        admin_data, admin_token = await _create_admin(client)
        return admin_token

    async def _setup_streamer_application(self, client):
        """Create a streamer, apply for verification, return (streamer_data, token)."""
        streamer, token = await _register_and_login(
            client, {"username": f"s_{int(time.time())}", "role": "streamer"}
        )
        await client.post(
            "/api/users/me/apply-streamer",
            json={"real_name": "李四", "id_number": "320102199001011234"},
            headers=_auth_headers(token),
        )
        return streamer, token

    @pytest.mark.asyncio
    async def test_admin_approve_streamer(self, client):
        admin_token = await self._get_admin_token(client)
        streamer, _ = await self._setup_streamer_application(client)

        r = await client.post(
            f"/api/admin/streamers/{streamer['id']}/verify",
            json={"approved": True},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0
        assert r.json()["data"]["status"] == "approved"

        # Check streamer is now verified
        profile = await client.get(f"/api/users/{streamer['id']}")
        assert profile.json()["data"]["streamer_verified"] is True

    @pytest.mark.asyncio
    async def test_admin_reject_streamer(self, client):
        admin_token = await self._get_admin_token(client)
        streamer, _ = await self._setup_streamer_application(client)

        r = await client.post(
            f"/api/admin/streamers/{streamer['id']}/verify",
            json={"approved": False, "reject_reason": "信息不匹配"},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "rejected"

        # Streamer should NOT be verified
        profile = await client.get(f"/api/users/{streamer['id']}")
        assert profile.json()["data"]["streamer_verified"] is False

    @pytest.mark.asyncio
    async def test_reject_without_reason_fails(self, client):
        admin_token = await self._get_admin_token(client)
        streamer, _ = await self._setup_streamer_application(client)

        r = await client.post(
            f"/api/admin/streamers/{streamer['id']}/verify",
            json={"approved": False},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_no_application(self, client):
        admin_token = await self._get_admin_token(client)
        streamer, _ = await _register_and_login(
            client, {"username": "s_noapp", "role": "streamer"}
        )

        r = await client.post(
            f"/api/admin/streamers/{streamer['id']}/verify",
            json={"approved": True},
            headers=_auth_headers(admin_token),
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_non_admin_cannot_verify(self, client):
        _, token = await _register_and_login(client)

        r = await client.post(
            "/api/admin/streamers/1/verify",
            json={"approved": True},
            headers=_auth_headers(token),
        )
        assert r.status_code == 403


# ── ID Number Masking ──────────────────────────────────────────────


class TestIdNumberMasking:
    @pytest.mark.asyncio
    async def test_standard_id_masking(self, client):
        """Standard 18-digit ID should mask middle digits."""
        _, token = await _register_and_login(
            client, {"username": "streamer_mask", "role": "streamer"}
        )

        r = await client.post(
            "/api/users/me/apply-streamer",
            json={"real_name": "王五", "id_number": "320102199001011234"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        id_number = r.json()["data"]["id_number"]
        # Should be: "320**************234" format (mask showing first 3, last 4)
        assert id_number.startswith("320")
        assert id_number.endswith("1234")
        assert "*" * 11 in id_number  # 18 - 7 = 11 masked chars
