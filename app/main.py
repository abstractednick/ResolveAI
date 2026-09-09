"""ResolveAI FastAPI application."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from app.config import get_settings
from app.db import init_db
from app.middleware.metrics import REQUEST_COUNT, REQUEST_LATENCY, generate_latest, CONTENT_TYPE_LATEST
from app.middleware.rate_limit import rate_limit_dependency
from app.routes import api_router
from app.schemas import HealthResponse
from app.services.realtime import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resolveai")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.2)
        except Exception as exc:  # pragma: no cover
            logger.warning("Sentry init failed: %s", exc)
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    endpoint = request.url.path
    REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, endpoint).observe(elapsed)
    return response


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return HealthResponse(status="ok", version="1.0.0", env=settings.app_env)


@app.get("/ready", tags=["system"])
def ready():
    from sqlalchemy import text
    from app.db import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return PlainTextResponse(f"not ready: {exc}", status_code=503)


@app.get("/metrics", tags=["system"])
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws/{tenant_id}")
async def websocket_endpoint(tenant_id: str, websocket: WebSocket):
    await manager.connect(tenant_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(tenant_id, websocket)


app.include_router(api_router, prefix=settings.api_prefix, dependencies=[Depends(rate_limit_dependency)])


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_prefix,
    }
