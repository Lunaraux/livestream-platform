"""WebSocket real-time service module.

Components:
- connection_manager: tracks connections per room, viewer counts, heartbeats
- message_models: Pydantic models for WS message types
- message_handler: routes and processes incoming messages
- api endpoint: WS /ws/rooms/{room_id} with token auth
"""

from app.websocket.connection_manager import ConnectionManager, manager
from app.websocket.message_handler import (
    broadcast_announcement,
    broadcast_gift,
    broadcast_room_banned,
    broadcast_user_enter,
    handle_message,
)
from app.websocket.message_models import make_server_message

__all__ = [
    "ConnectionManager",
    "manager",
    "broadcast_announcement",
    "broadcast_gift",
    "broadcast_room_banned",
    "broadcast_user_enter",
    "handle_message",
    "make_server_message",
]
