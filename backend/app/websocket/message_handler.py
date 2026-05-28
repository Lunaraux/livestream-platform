"""WebSocket message handler — routes, validates, and processes incoming messages.

Per 07-realtime.md: handles ping/pong, danmaku, like messages.
Delegates business logic to InteractionService and broadcasts via ConnectionManager.
"""

from __future__ import annotations

import json
import time

from fastapi import WebSocket
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.models.user import User
from app.services.interaction_service import InteractionService
from app.websocket.connection_manager import ConnectedClient, manager
from app.websocket.message_models import (
    CLIENT_MESSAGE_TYPES,
    DanmakuMessage,
    LikeMessage,
    PingMessage,
    make_server_message,
)


def _now_ts() -> int:
    return int(time.time())


async def handle_message(raw_text: str, client: ConnectedClient, room_id: int) -> None:
    """Parse, validate, and dispatch a single incoming WS message.

    Args:
        raw_text: Raw JSON text from the WebSocket.
        client: The connected client (has websocket, user).
        room_id: Room ID the client is connected to.
    """
    # Parse JSON
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        await manager.send_personal(
            client.websocket,
            make_server_message("error", message="无效的JSON格式", code=1001),
        )
        return

    # Validate message type
    msg_type = payload.get("type", "")
    msg_data = payload.get("data", {})

    if msg_type not in CLIENT_MESSAGE_TYPES:
        await manager.send_personal(
            client.websocket,
            make_server_message("error", message=f"未知的消息类型: {msg_type}", code=1001),
        )
        return

    # Route to handler
    try:
        if msg_type == "ping":
            await _handle_ping(client)
        elif msg_type == "danmaku":
            await _handle_danmaku(client, room_id, msg_data)
        elif msg_type == "like":
            await _handle_like(client, room_id)
    except AppException as e:
        await manager.send_personal(
            client.websocket,
            make_server_message("error", message=e.message, code=e.code),
        )
    except Exception:
        await manager.send_personal(
            client.websocket,
            make_server_message("error", message="服务器内部错误", code=9999),
        )


# ── Message handlers ─────────────────────────────────────────────


async def _handle_ping(client: ConnectedClient) -> None:
    """Respond to heartbeat ping with pong + server timestamp."""
    manager.update_heartbeat(client.websocket)
    await manager.send_personal(
        client.websocket,
        make_server_message("pong", server_time=_now_ts()),
    )


async def _handle_danmaku(
    client: ConnectedClient,
    room_id: int,
    data: dict,
) -> None:
    """Handle danmaku send: validate, persist, broadcast.

    Guests (unauthenticated) cannot send danmaku.
    Rate limits and forbidden words are enforced by InteractionService.
    """
    if not client.authenticated or client.user is None:
        await manager.send_personal(
            client.websocket,
            make_server_message("error", message="游客不能发送弹幕，请先登录", code=1002),
        )
        return

    # Validate message data with Pydantic
    try:
        msg = DanmakuMessage.model_validate({"type": "danmaku", "data": data})
    except PydanticValidationError as e:
        errors = []
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            errors.append(f"{field}: {err['msg']}")
        await manager.send_personal(
            client.websocket,
            make_server_message("error", message=f"弹幕参数错误: {'; '.join(errors)}", code=1001),
        )
        return

    # Use InteractionService for business logic (validation, rate limits, persistence)
    async with async_session_factory() as db:
        svc = InteractionService(db)
        try:
            result = await svc.send_danmaku(
                user=client.user,
                room_id=room_id,
                content=msg.data.content,
                color=msg.data.color,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    # Broadcast to all clients in room
    broadcast_msg = make_server_message(
        "danmaku",
        user_id=result.user_id,
        nickname=result.nickname,
        level=client.level,
        content=result.content,
        color=result.color,
    )
    await manager.broadcast(room_id, broadcast_msg)


async def _handle_like(
    client: ConnectedClient,
    room_id: int,
) -> None:
    """Handle like: increment count, broadcast updated total.

    Guests cannot send likes.
    Max 1000 per user per session enforced by InteractionService.
    """
    if not client.authenticated or client.user is None:
        await manager.send_personal(
            client.websocket,
            make_server_message("error", message="游客不能点赞，请先登录", code=1002),
        )
        return

    # Use InteractionService for business logic
    async with async_session_factory() as db:
        svc = InteractionService(db)
        try:
            result = await svc.like_room(
                user=client.user,
                room_id=room_id,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    # Get total like count from Redis for broadcast
    total_likes = await svc.get_like_count(room_id)

    # Broadcast total like count to all clients in room
    broadcast_msg = make_server_message("like", count=total_likes)
    await manager.broadcast(room_id, broadcast_msg)


# ── Room event helpers ───────────────────────────────────────────


async def broadcast_user_enter(client: ConnectedClient, room_id: int) -> None:
    """Broadcast user_enter for high-level users (level >= 5)."""
    if client.level >= 5:
        await manager.broadcast(
            room_id,
            make_server_message(
                "user_enter",
                nickname=client.nickname,
                level=client.level,
            ),
        )


async def broadcast_announcement(room_id: int, content: str) -> None:
    """Broadcast a system announcement to all clients in a room."""
    await manager.broadcast(
        room_id,
        make_server_message("announcement", content=content),
    )


async def broadcast_gift(
    room_id: int,
    user_id: int,
    nickname: str,
    gift_name: str,
    quantity: int,
    total_fen: int,
    is_special: bool = False,
) -> None:
    """Broadcast a gift event to all clients in a room.

    Args:
        is_special: If True, sends gift_special (full-screen) instead of gift.
    """
    if is_special:
        msg = make_server_message(
            "gift_special",
            user_id=user_id,
            nickname=nickname,
            gift_name=gift_name,
            quantity=quantity,
            total_fen=total_fen,
            effect_type="fullscreen",
        )
    else:
        msg = make_server_message(
            "gift",
            user_id=user_id,
            nickname=nickname,
            gift_name=gift_name,
            quantity=quantity,
            total_fen=total_fen,
        )
    await manager.broadcast(room_id, msg)


async def broadcast_room_banned(room_id: int, reason: str) -> None:
    """Kick all clients with a room_banned message."""
    await manager.kick_all(room_id, reason)
