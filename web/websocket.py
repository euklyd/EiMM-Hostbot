"""WebSocket connection manager for real-time updates."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Information about a WebSocket connection."""

    websocket: WebSocket
    user_id: int
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ConnectionManager:
    """Manages WebSocket connections grouped by server ID."""

    def __init__(self) -> None:
        # server_id -> list of connections
        self._connections: dict[int, list[ConnectionInfo]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, server_id: int, user_id: int) -> None:
        """Accept a WebSocket connection and add it to the server's room."""
        await websocket.accept()
        conn = ConnectionInfo(websocket=websocket, user_id=user_id)
        self._connections[server_id].append(conn)
        logger.debug(f"WebSocket connected: user {user_id} to server {server_id}")

    def disconnect(self, websocket: WebSocket, server_id: int) -> None:
        """Remove a WebSocket connection from the server's room."""
        connections = self._connections[server_id]
        self._connections[server_id] = [c for c in connections if c.websocket != websocket]

        # Clean up empty rooms
        if not self._connections[server_id]:
            del self._connections[server_id]

        logger.debug(f"WebSocket disconnected from server {server_id}")

    def get_connection_count(self, server_id: int) -> int:
        """Get the number of connections for a server."""
        return len(self._connections.get(server_id, []))

    async def broadcast(self, server_id: int, event_type: str, data: Any = None) -> int:
        """Broadcast a message to all connections for a server.

        Args:
            server_id: The server to broadcast to.
            event_type: The type of event (e.g., "new_question", "question_answered").
            data: Optional data payload for the event.

        Returns:
            Number of clients the message was sent to.
        """
        connections = self._connections.get(server_id, [])
        if not connections:
            return 0

        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        sent_count = 0
        failed_connections = []

        for conn in connections:
            try:
                await conn.websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                failed_connections.append(conn)

        # Clean up failed connections
        for conn in failed_connections:
            self._connections[server_id] = [c for c in self._connections[server_id] if c != conn]

        return sent_count

    async def send_to_user(self, server_id: int, user_id: int, event_type: str, data: Any = None) -> bool:
        """Send a message to a specific user in a server.

        Args:
            server_id: The server the user is connected to.
            user_id: The user to send to.
            event_type: The type of event.
            data: Optional data payload.

        Returns:
            True if message was sent, False if user not connected.
        """
        connections = self._connections.get(server_id, [])

        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        for conn in connections:
            if conn.user_id == user_id:
                try:
                    await conn.websocket.send_json(message)
                    return True
                except Exception as e:
                    logger.warning(f"Failed to send to user {user_id}: {e}")
                    return False

        return False


# Global connection manager instance
manager = ConnectionManager()


async def websocket_endpoint(
    websocket: WebSocket,
    server_id: int,
    user_id: int,
) -> None:
    """Handle a WebSocket connection for real-time interview updates.

    This function should be called from a route handler after authentication.
    """
    await manager.connect(websocket, server_id, user_id)

    try:
        while True:
            # Keep connection alive and handle any client messages
            data = await websocket.receive_text()
            # Could handle client->server messages here (e.g., typing indicators)
            # For now, we just acknowledge
            logger.debug(f"Received WebSocket message from {user_id}: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, server_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, server_id)
