"""In-memory WebSocket fan-out for live dashboard updates."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, tenant_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms.setdefault(tenant_id, set()).add(websocket)

    async def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._rooms.get(tenant_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._rooms.pop(tenant_id, None)

    async def broadcast(self, tenant_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._rooms.get(tenant_id, set()))
        dead: list[WebSocket] = []
        data = json.dumps(payload)
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(tenant_id, ws)


manager = ConnectionManager()


def broadcast_tenant(tenant_id: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget from sync Celery/service code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast(tenant_id, payload))
        else:
            loop.run_until_complete(manager.broadcast(tenant_id, payload))
    except RuntimeError:
        logger.debug("No event loop for websocket broadcast: %s", payload.get("type"))
