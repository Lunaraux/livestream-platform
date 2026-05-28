"""WebSocket connection manager — tracks per-room connections, viewer counts, heartbeats.

Implements 07-realtime.md:
- WS /ws/rooms/{room_id} with token query param
- Redis INCR/DECR for viewer counts
- Ping/pong heartbeat (90s timeout)
- Guest connections (authenticated=False)
- Broadcast to all connections in a room
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.config import settings
from app.core.redis import get_redis
from app.models.user import User

# Per spec: 90s heartbeat timeout, 30s broadcast interval
HEARTBEAT_TIMEOUT = 90
VIEWER_BROADCAST_INTERVAL = 30

# Redis key pattern (consistent with room_service.py)
ROOM_VIEWERS_KEY = "room:{room_id}:viewers"


@dataclass(eq=False)
class ConnectedClient:
    """A single WebSocket connection in a room.

    Uses eq=False so the default __hash__ (based on id) is preserved.
    This lets us store clients in a set if needed, though we use dicts internally.
    """

    websocket: WebSocket
    user_id: int | None  # None for guest (unauthenticated)
    user: User | None    # Full User object (None for guest)
    authenticated: bool
    last_heartbeat: float = field(default_factory=time.time)

    @property
    def nickname(self) -> str:
        if self.user:
            return self.user.nickname
        return "游客"

    @property
    def level(self) -> int:
        if self.user:
            return self.user.level
        return 1


def _ws_key(ws: WebSocket) -> int:
    """Return a stable integer key for a WebSocket."""
    return id(ws)


class ConnectionManager:
    """Manages WebSocket connections grouped by room_id.

    Singleton — all WS endpoints share the same instance.
    """

    def __init__(self) -> None:
        # room_id -> dict[ws_key, ConnectedClient]
        self._rooms: dict[int, dict[int, ConnectedClient]] = {}
        # WebSocket key -> room_id reverse lookup
        self._ws_to_room: dict[int, int] = {}
        # Lock for thread-safe mutation
        self._lock = asyncio.Lock()

    # ── Connection lifecycle ──────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        room_id: int,
        user: User | None = None,
    ) -> None:
        """Accept a new WebSocket connection and register it in the room.

        Args:
            websocket: The FastAPI WebSocket connection.
            room_id: Room ID to join.
            user: Authenticated User (None for guest).
        """
        client = ConnectedClient(
            websocket=websocket,
            user_id=user.id if user else None,
            user=user,
            authenticated=user is not None,
        )

        key = _ws_key(websocket)
        async with self._lock:
            if room_id not in self._rooms:
                self._rooms[room_id] = {}
            self._rooms[room_id][key] = client
            self._ws_to_room[key] = room_id

        # Increment viewer count in Redis
        await self._incr_viewers(room_id, 1)

    async def disconnect(self, websocket: WebSocket) -> int | None:
        """Remove a WebSocket connection and return the room_id.

        Returns None if the websocket was not registered.
        """
        key = _ws_key(websocket)
        room_id = self._ws_to_room.pop(key, None)
        if room_id is None:
            return None

        async with self._lock:
            room = self._rooms.get(room_id, {})
            room.pop(key, None)

            # Clean up empty rooms
            if not room:
                self._rooms.pop(room_id, None)

        # Decrement viewer count in Redis
        await self._incr_viewers(room_id, -1)

        return room_id

    def update_heartbeat(self, websocket: WebSocket) -> None:
        """Mark a connection as alive."""
        key = _ws_key(websocket)
        room_id = self._ws_to_room.get(key)
        if room_id is None:
            return
        room = self._rooms.get(room_id, {})
        client = room.get(key)
        if client:
            client.last_heartbeat = time.time()

    # ── Broadcasting ──────────────────────────────────────────────

    async def broadcast(self, room_id: int, message: dict) -> int:
        """Send a JSON message to all connected clients in a room.

        Returns the number of clients the message was sent to.
        Sent count includes only successful sends (dead connections are removed).
        """
        async with self._lock:
            room = dict(self._rooms.get(room_id, {}))

        sent = 0
        dead: list[int] = []

        for key, client in room.items():
            try:
                await client.websocket.send_json(message)
                sent += 1
            except Exception:
                dead.append(key)

        # Clean up dead connections
        if dead:
            async with self._lock:
                room_set = self._rooms.get(room_id, {})
                for dk in dead:
                    room_set.pop(dk, None)
                    self._ws_to_room.pop(dk, None)

        return sent

    async def broadcast_viewer_count(self, room_id: int) -> int:
        """Broadcast the current viewer count to all clients in a room."""
        count = await self.get_viewer_count(room_id)
        message = {"type": "viewer_update", "data": {"count": count}}
        return await self.broadcast(room_id, message)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """Send a JSON message to a single client."""
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)

    # ── Connection queries ────────────────────────────────────────

    def get_connections(self, room_id: int) -> list[ConnectedClient]:
        """Return a snapshot of connected clients in a room."""
        return list(self._rooms.get(room_id, {}).values())

    def get_user_client(self, room_id: int, websocket: WebSocket) -> ConnectedClient | None:
        """Find the ConnectedClient for a specific WebSocket in a room."""
        return self._rooms.get(room_id, {}).get(_ws_key(websocket))

    def get_connection_count(self, room_id: int) -> int:
        """Return the number of connected clients in a room from memory."""
        return len(self._rooms.get(room_id, {}))

    # ── Viewer count (Redis) ──────────────────────────────────────

    @staticmethod
    async def _incr_viewers(room_id: int, delta: int) -> int:
        """Increment/decrement viewer count in Redis. Returns new count."""
        r = await get_redis()
        return await r.incrby(ROOM_VIEWERS_KEY.format(room_id=room_id), delta)

    @staticmethod
    async def get_viewer_count(room_id: int) -> int:
        """Get current viewer count from Redis."""
        r = await get_redis()
        val = await r.get(ROOM_VIEWERS_KEY.format(room_id=room_id))
        return int(val) if val else 0

    @staticmethod
    async def reset_viewer_count(room_id: int) -> None:
        """Reset viewer count in Redis (used when stream ends)."""
        r = await get_redis()
        await r.delete(ROOM_VIEWERS_KEY.format(room_id=room_id))

    # ── Heartbeat monitoring ─────────────────────────────────────

    async def check_heartbeats(self, room_id: int) -> list[WebSocket]:
        """Find and disconnect clients that have timed out.

        Returns list of WebSockets that were disconnected due to timeout.
        """
        now = time.time()
        dead: list[WebSocket] = []

        async with self._lock:
            room = self._rooms.get(room_id, {})
            for key, client in list(room.items()):
                if now - client.last_heartbeat > HEARTBEAT_TIMEOUT:
                    dead.append(client.websocket)
                    del room[key]
                    self._ws_to_room.pop(key, None)

        # Decrement viewer count for each dead connection
        for _ in dead:
            await self._incr_viewers(room_id, -1)

        return dead

    # ── Room lifecycle ────────────────────────────────────────────

    async def kick_all(self, room_id: int, reason: str = "") -> None:
        """Force-disconnect all clients in a room (e.g., room banned)."""
        async with self._lock:
            room = self._rooms.pop(room_id, {})

        for key, client in room.items():
            try:
                if reason:
                    await client.websocket.send_json({
                        "type": "room_banned",
                        "data": {"reason": reason},
                    })
                await client.websocket.close()
            except Exception:
                pass
            self._ws_to_room.pop(key, None)

    async def start_viewer_broadcast(self, room_id: int) -> asyncio.Task:
        """Start a periodic background task to broadcast viewer count every 30s.

        Returns the asyncio Task so it can be cancelled on disconnect.
        """

        async def _broadcast_loop() -> None:
            while True:
                await asyncio.sleep(VIEWER_BROADCAST_INTERVAL)
                # Check if room still has connections
                if self.get_connection_count(room_id) == 0:
                    break
                # Kick dead connections first, then broadcast
                await self.check_heartbeats(room_id)
                await self.broadcast_viewer_count(room_id)

        return asyncio.create_task(_broadcast_loop())


# Singleton instance
manager = ConnectionManager()
