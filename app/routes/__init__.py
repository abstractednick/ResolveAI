from fastapi import APIRouter

from app.routes import admin, auth, public, tickets, webhooks, widget

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tickets.router)
api_router.include_router(webhooks.router)
api_router.include_router(widget.router)
api_router.include_router(admin.router)
api_router.include_router(public.router)
