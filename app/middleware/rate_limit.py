"""Simple in-memory sliding-window rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.config import get_settings

settings = get_settings()
_lock = Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def _allow(key: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.time()
    with _lock:
        q = _buckets[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


async def rate_limit_dependency(request: Request) -> None:
    tenant = request.headers.get("X-Tenant-Key") or request.client.host if request.client else "anon"
    path_key = f"{tenant}:{request.url.path}"
    limit = settings.widget_rate_limit_per_minute if "/widget/" in request.url.path else settings.rate_limit_per_minute
    if not _allow(path_key, limit):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
