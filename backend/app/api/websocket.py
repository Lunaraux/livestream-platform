"""WebSocket API endpoint — WS /ws/rooms/{room_id}.

Per 07-realtime.md:
- Token authentication via query param (?token=xxx)
- Guest access allowed (receive-only)
- Connects to room, handles message loop, cleans up on disconnect
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.security import decode_access_token
from app.models.room import Room
from app.models.user import User
from app.websocket.connection_manager import HEARTBEAT_TIMEOUT, manager
from app.websocket.message_handler import broadcast_user_enter, handle_message

router = APIRouter()


async def _authenticate_token(token: str, db: AsyncSession) -> User | None:
    """Validate a JWT token and return the user.

    Returns None for any auth failure (expired, invalid, banned, etc.)
    to allow guest access.
    """
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    result = await db.execute(
        select(User).where(User.id == int(user_id), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None

    if user.is_banned:
        return None

    if user.locked_until and user.locked_until > int(time.time()):
        return None

    return user


async def _get_room(db: AsyncSession, room_id: int) -> Room | None:
    """Get a non-deleted room by ID."""
    result = await db.execute(
        select(Room).where(Room.id == room_id, Room.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


@router.websocket("/ws/rooms/{room_id}")
async def websocket_room(
    websocket: WebSocket,
    room_id: int,
    token: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint for room real-time communication.

    Query params:
        token: JWT access token for authentication (optional for guests).

    Message protocol per 07-realtime.md:
    - Client→Server: {type, data} for ping, danmaku, like
    - Server→Client: {type, data} for pong, danmaku, like, viewer_update, etc.
    """
    # ── Validate room and authenticate user ──────────────────────
    # Use a short-lived session for initial validation only
    user: User | None = None
    async with async_session_factory() as db:
        room = await _get_room(db, room_id)
        if room is None:
            await websocket.close(code=4004, reason="直播间不存在")
            return

        if token:
            user = await _authenticate_token(token, db)
        # Commit to release connection back to pool
        await db.commit()

    # ── Accept connection ────────────────────────────────────────
    await websocket.accept()
    await manager.connect(websocket, room_id, user)

    # Broadcast high-level user entry
    connected_client = manager.get_user_client(room_id, websocket)
    if connected_client:
        await broadcast_user_enter(connected_client, room_id)

    # Send initial viewer count to the new client
    viewer_count = await manager.get_viewer_count(room_id)
    await manager.send_personal(
        websocket,
        {"type": "viewer_update", "data": {"count": viewer_count}},
    )

    # ── Message loop ─────────────────────────────────────────────
    try:
        while True:
            # Wait for message
            raw_text = await websocket.receive_text()

            client = manager.get_user_client(room_id, websocket)
            if client is None:
                break  # Client was removed (shouldn't normally happen)

            await handle_message(raw_text, client, room_id)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Cleanup: disconnect client, update viewer count
        await manager.disconnect(websocket)
        await manager.broadcast_viewer_count(room_id)
