"""Tests for WebSocket real-time service.

Tests cover:
- Connection manager: connect/disconnect, viewer count, heartbeat
- Message models: Pydantic validation
- WebSocket API: auth, ping/pong, danmaku, like, disconnect
- Broadcast helpers: gift, announcement, room_banned

Uses in-memory SQLite + mocked Redis.
"""

from __future__ import annotations

import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models.interaction import Gift
from app.models.room import Room
from app.models.user import User, Wallet
from app.websocket.connection_manager import ConnectionManager, manager
from app.websocket.message_models import (
    DanmakuBroadcastData,
    DanmakuMessage,
    ErrorData,
    LikeBroadcastData,
    LikeMessage,
    PingMessage,
    PongData,
    ViewerUpdateData,
    make_server_message,
)
from tests.conftest import test_session_factory


# =====================================================================
# Test Helpers
# =====================================================================


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_verified_streamer(app) -> tuple[dict, str]:
    uname = f"s{int(time.time() * 1000) % 1000000000}"
    now = int(time.time())
    async with test_session_factory() as session:
        user = User(
            username=uname, password_hash=hash_password("pass1234"),
            nickname="测试主播", role="streamer", streamer_verified=True,
            created_at=now, updated_at=now,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        wallet = Wallet(user_id=user.id, balance_fen=100000, created_at=now, updated_at=now)
        session.add(wallet)
        await session.commit()
        access_token, _ = create_access_token({"sub": str(user.id), "jti": str(uuid.uuid4())})
        return {"id": user.id, "username": uname}, access_token


async def _create_audience(app) -> tuple[dict, str]:
    uname = f"a{int(time.time() * 1000) % 1000000000}"
    now = int(time.time())
    async with test_session_factory() as session:
        user = User(
            username=uname, password_hash=hash_password("pass1234"),
            nickname="测试观众", role="audience", created_at=now, updated_at=now,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        wallet = Wallet(user_id=user.id, balance_fen=100000, created_at=now, updated_at=now)
        session.add(wallet)
        await session.commit()
        access_token, _ = create_access_token({"sub": str(user.id), "jti": str(uuid.uuid4())})
        return {"id": user.id, "username": uname}, access_token


async def _create_room_and_start(app, streamer_token: str) -> dict:
    client = TestClient(app)
    r = client.post("/api/rooms", json={"title": "测试直播间", "category": "game"},
                    headers=_auth_headers(streamer_token))
    assert r.status_code == 200, f"Create room failed: {r.json()}"
    room_id = r.json()["data"]["id"]
    r2 = client.post(f"/api/rooms/{room_id}/start", headers=_auth_headers(streamer_token))
    assert r2.status_code == 200, f"Start stream failed: {r2.json()}"
    return r2.json()["data"]


# =====================================================================
# Connection Manager Unit Tests
# =====================================================================


class TestConnectionManager:

    @pytest.fixture(autouse=True)
    async def _patch_redis(self):
        store: dict[str, str] = {}
        async def _incrby(key, amount):
            current = int(store.get(key, 0))
            store[key] = str(current + amount)
            return current + amount
        async def _get(key): return store.get(key)
        async def _delete(key): store.pop(key, None)
        mock = AsyncMock()
        mock.incrby = AsyncMock(side_effect=_incrby)
        mock.get = AsyncMock(side_effect=_get)
        mock.delete = AsyncMock(side_effect=_delete)
        mock.aclose = AsyncMock()
        async def _mock_get_redis(): return mock
        import app.websocket.connection_manager as cm
        old = cm.get_redis
        cm.get_redis = _mock_get_redis
        try: yield
        finally: cm.get_redis = old

    def _mock_ws(self): return MagicMock(send_json=AsyncMock(), close=AsyncMock(), receive_text=AsyncMock())

    @pytest.mark.asyncio
    async def test_connect_adds_to_room(self):
        mgr, ws, ws2 = ConnectionManager(), self._mock_ws(), self._mock_ws()
        await mgr.connect(ws, room_id=1); await mgr.connect(ws2, room_id=1)
        assert mgr.get_connection_count(1) == 2
        assert len(mgr.get_connections(1)) == 2

    @pytest.mark.asyncio
    async def test_connect_guest(self):
        mgr, ws = ConnectionManager(), self._mock_ws()
        await mgr.connect(ws, room_id=1, user=None)
        c = mgr.get_connections(1)[0]
        assert c.authenticated is False and c.user is None and c.user_id is None

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_room(self):
        mgr, ws = ConnectionManager(), self._mock_ws()
        await mgr.connect(ws, room_id=1)
        assert mgr.get_connection_count(1) == 1
        assert await mgr.disconnect(ws) == 1
        assert mgr.get_connection_count(1) == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_ws_returns_none(self):
        mgr = ConnectionManager()
        assert await mgr.disconnect(self._mock_ws()) is None

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        mgr, ws1, ws2 = ConnectionManager(), self._mock_ws(), self._mock_ws()
        await mgr.connect(ws1, room_id=1); await mgr.connect(ws2, room_id=1)
        msg = {"type": "test", "data": {"hello": "world"}}
        assert await mgr.broadcast(1, msg) == 2
        ws1.send_json.assert_called_once_with(msg)
        ws2.send_json.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_handles_dead_connections(self):
        mgr, ws1, ws2 = ConnectionManager(), self._mock_ws(), self._mock_ws()
        ws2.send_json.side_effect = Exception("lost")
        await mgr.connect(ws1, room_id=1); await mgr.connect(ws2, room_id=1)
        assert await mgr.broadcast(1, {"type": "test", "data": {}}) == 1
        assert mgr.get_connection_count(1) == 1

    @pytest.mark.asyncio
    async def test_broadcast_viewer_count(self):
        mgr, ws = ConnectionManager(), self._mock_ws()
        await mgr.connect(ws, room_id=1)
        await mgr.broadcast_viewer_count(1)
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "viewer_update"
        assert "count" in call_args["data"]

    @pytest.mark.asyncio
    async def test_update_heartbeat(self):
        mgr, ws = ConnectionManager(), self._mock_ws()
        await mgr.connect(ws, room_id=1)
        old = mgr.get_connections(1)[0].last_heartbeat
        mgr.update_heartbeat(ws)
        assert mgr.get_connections(1)[0].last_heartbeat >= old

    @pytest.mark.asyncio
    async def test_kick_all_disconnects_everyone(self):
        mgr, ws1, ws2 = ConnectionManager(), self._mock_ws(), self._mock_ws()
        await mgr.connect(ws1, room_id=1); await mgr.connect(ws2, room_id=1)
        await mgr.kick_all(1, reason="封禁")
        ws1.send_json.assert_called(); ws1.close.assert_called_once()
        ws2.close.assert_called_once()
        assert mgr.get_connection_count(1) == 0

    @pytest.mark.asyncio
    async def test_multiple_rooms_independent(self):
        mgr, ws1, ws2 = ConnectionManager(), self._mock_ws(), self._mock_ws()
        await mgr.connect(ws1, room_id=1); await mgr.connect(ws2, room_id=2)
        assert mgr.get_connection_count(1) == 1
        assert mgr.get_connection_count(2) == 1
        await mgr.broadcast(1, {"type": "test"})
        ws1.send_json.assert_called(); ws2.send_json.assert_not_called()


# =====================================================================
# Message Model Tests
# =====================================================================


class TestMessageModels:

    def test_ping_message_parses(self):
        assert PingMessage.model_validate({"type": "ping"}).type == "ping"

    def test_danmaku_message_parses(self):
        msg = DanmakuMessage.model_validate({"type": "danmaku", "data": {"content": "你好", "color": "#ff0000"}})
        assert msg.data.content == "你好" and msg.data.color == "#ff0000"

    def test_danmaku_message_default_color(self):
        msg = DanmakuMessage.model_validate({"type": "danmaku", "data": {"content": "测试"}})
        assert msg.data.color == "#ffffff"

    def test_danmaku_content_too_long(self):
        with pytest.raises(Exception):
            DanmakuMessage.model_validate({"type": "danmaku", "data": {"content": "x" * 201}})

    def test_danmaku_empty_content(self):
        with pytest.raises(Exception):
            DanmakuMessage.model_validate({"type": "danmaku", "data": {"content": ""}})

    def test_like_message_parses(self):
        assert LikeMessage.model_validate({"type": "like", "data": {}}).type == "like"

    def test_make_server_message_pong(self):
        msg = make_server_message("pong", server_time=1234567890)
        assert msg["type"] == "pong" and msg["data"]["server_time"] == 1234567890

    def test_make_server_message_danmaku(self):
        msg = make_server_message("danmaku", user_id=1, nickname="A", level=3, content="hi", color="#fff")
        assert msg["data"]["nickname"] == "A"

    def test_make_server_message_like(self):
        assert make_server_message("like", count=42)["data"]["count"] == 42

    def test_make_server_message_viewer_update(self):
        assert make_server_message("viewer_update", count=100)["data"]["count"] == 100

    def test_make_server_message_error(self):
        msg = make_server_message("error", message="err", code=1002)
        assert msg["data"]["code"] == 1002

    def test_make_server_message_room_banned(self):
        assert make_server_message("room_banned", reason="bad")["data"]["reason"] == "bad"

    def test_make_server_message_unknown_type_fallback(self):
        msg = make_server_message("custom", foo="bar")
        assert msg["type"] == "custom" and msg["data"]["foo"] == "bar"


# =====================================================================
# WebSocket API Integration Tests
# =====================================================================


class TestWebSocketAPI:

    def _ws_client(self, app): return TestClient(app)

    @staticmethod
    def _skip_viewer_update(ws):
        """Consume the one viewer_update sent on connect."""
        data = ws.receive_json()
        assert data["type"] == "viewer_update", f"Expected viewer_update, got {data['type']}"

    @pytest.mark.asyncio
    async def test_ws_connect_as_guest(self, app):
        _, token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, token)
        client = self._ws_client(app)
        with client.websocket_connect(f"/ws/rooms/{room['id']}") as ws:
            self._skip_viewer_update(ws)
            ws.send_json({"type": "ping", "data": {}})
            data = ws.receive_json()
            assert data["type"] == "pong"
            assert "server_time" in data["data"]

    @pytest.mark.asyncio
    async def test_ws_connect_authenticated(self, app):
        _, audience_token = await _create_audience(app)
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        client = self._ws_client(app)
        with client.websocket_connect(f"/ws/rooms/{room['id']}?token={audience_token}") as ws:
            self._skip_viewer_update(ws)
            ws.send_json({"type": "ping", "data": {}})
            assert ws.receive_json()["type"] == "pong"

    @pytest.mark.asyncio
    async def test_ws_connect_nonexistent_room(self, app):
        with pytest.raises(Exception):
            with self._ws_client(app).websocket_connect("/ws/rooms/99999"):
                pass

    @pytest.mark.asyncio
    async def test_ws_send_danmaku_authenticated(self, app):
        _, audience_token = await _create_audience(app)
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        with self._ws_client(app).websocket_connect(
            f"/ws/rooms/{room['id']}?token={audience_token}"
        ) as ws:
            self._skip_viewer_update(ws)
            ws.send_json({"type": "danmaku", "data": {"content": "hello弹幕", "color": "#FFFFFF"}})
            data = ws.receive_json()
            assert data["type"] == "danmaku"
            assert data["data"]["content"] == "hello弹幕"

    @pytest.mark.asyncio
    async def test_ws_send_danmaku_guest_blocked(self, app):
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        with self._ws_client(app).websocket_connect(f"/ws/rooms/{room['id']}") as ws:
            self._skip_viewer_update(ws)
            ws.send_json({"type": "danmaku", "data": {"content": "guest", "color": "#fff"}})
            data = ws.receive_json()
            assert data["type"] == "error" and data["data"]["code"] == 1002

    @pytest.mark.asyncio
    async def test_ws_send_like_authenticated(self, app):
        _, audience_token = await _create_audience(app)
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        with self._ws_client(app).websocket_connect(
            f"/ws/rooms/{room['id']}?token={audience_token}"
        ) as ws:
            self._skip_viewer_update(ws)
            ws.send_json({"type": "like", "data": {}})
            data = ws.receive_json()
            assert data["type"] == "like" and data["data"]["count"] >= 1

    @pytest.mark.asyncio
    async def test_ws_send_like_guest_blocked(self, app):
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        with self._ws_client(app).websocket_connect(f"/ws/rooms/{room['id']}") as ws:
            self._skip_viewer_update(ws)
            ws.send_json({"type": "like", "data": {}})
            assert ws.receive_json()["data"]["code"] == 1002

    @pytest.mark.asyncio
    async def test_ws_invalid_json(self, app):
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        with self._ws_client(app).websocket_connect(f"/ws/rooms/{room['id']}") as ws:
            self._skip_viewer_update(ws)
            ws.send_text("not json {{{")
            assert "JSON" in ws.receive_json()["data"]["message"]

    @pytest.mark.asyncio
    async def test_ws_unknown_message_type(self, app):
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        with self._ws_client(app).websocket_connect(f"/ws/rooms/{room['id']}") as ws:
            self._skip_viewer_update(ws)
            ws.send_json({"type": "unknown", "data": {}})
            assert "未知" in ws.receive_json()["data"]["message"]

    @pytest.mark.asyncio
    async def test_ws_disconnect_updates_viewer_count(self, app):
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        client = self._ws_client(app)
        with client.websocket_connect(f"/ws/rooms/{room['id']}") as ws:
            data = ws.receive_json()
            assert data["type"] == "viewer_update"
        # Reconnect and check count
        with client.websocket_connect(f"/ws/rooms/{room['id']}") as ws2:
            data = ws2.receive_json()
            assert data["data"]["count"] >= 0

    @pytest.mark.asyncio
    async def test_ws_multiple_clients_same_room(self, app):
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        client = self._ws_client(app)
        with (client.websocket_connect(f"/ws/rooms/{room['id']}") as ws1,
              client.websocket_connect(f"/ws/rooms/{room['id']}") as ws2):
            self._skip_viewer_update(ws1)
            self._skip_viewer_update(ws2)
            ws1.send_json({"type": "ping", "data": {}})
            assert ws1.receive_json()["type"] == "pong"
            ws2.send_json({"type": "ping", "data": {}})
            assert ws2.receive_json()["type"] == "pong"

    @pytest.mark.asyncio
    async def test_ws_ping_pong_heartbeat(self, app):
        _, streamer_token = await _create_verified_streamer(app)
        room = await _create_room_and_start(app, streamer_token)
        with self._ws_client(app).websocket_connect(f"/ws/rooms/{room['id']}") as ws:
            self._skip_viewer_update(ws)
            for _ in range(3):
                ws.send_json({"type": "ping", "data": {}})
                data = ws.receive_json()
                assert data["type"] == "pong"
                assert isinstance(data["data"]["server_time"], int)


# =====================================================================
# Broadcast Helper Tests
# =====================================================================


class TestBroadcastHelpers:

    @pytest.mark.asyncio
    async def test_broadcast_gift(self, app):
        mgr, ws = ConnectionManager(), MagicMock(send_json=AsyncMock())
        await mgr.connect(ws, room_id=1)
        from app.websocket.message_handler import broadcast_gift
        import app.websocket.message_handler as handler
        old = handler.manager; handler.manager = mgr
        try:
            await broadcast_gift(1, 1, "User", "火箭", 1, 10000)
            ws.send_json.assert_called_once()
            msg = ws.send_json.call_args[0][0]
            assert msg["type"] == "gift" and msg["data"]["gift_name"] == "火箭"
        finally: handler.manager = old

    @pytest.mark.asyncio
    async def test_broadcast_gift_special(self, app):
        mgr, ws = ConnectionManager(), MagicMock(send_json=AsyncMock())
        await mgr.connect(ws, room_id=1)
        from app.websocket.message_handler import broadcast_gift
        import app.websocket.message_handler as handler
        old = handler.manager; handler.manager = mgr
        try:
            await broadcast_gift(1, 1, "VIP", "嘉年华", 1, 500000, is_special=True)
            msg = ws.send_json.call_args[0][0]
            assert msg["type"] == "gift_special" and msg["data"]["effect_type"] == "fullscreen"
        finally: handler.manager = old

    @pytest.mark.asyncio
    async def test_broadcast_announcement(self, app):
        mgr, ws = ConnectionManager(), MagicMock(send_json=AsyncMock())
        await mgr.connect(ws, room_id=1)
        import app.websocket.message_handler as handler
        old = handler.manager; handler.manager = mgr
        try:
            await handler.broadcast_announcement(1, "系统维护中")
            ws.send_json.assert_called_once()
            assert ws.send_json.call_args[0][0]["data"]["content"] == "系统维护中"
        finally: handler.manager = old
