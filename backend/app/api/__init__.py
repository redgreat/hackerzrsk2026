from fastapi import APIRouter

from app.api import admin, auth, scenarios, sessions, speech, stats, system, wecom

api_router = APIRouter(prefix="/api")
for module in (system, auth, scenarios, sessions, speech, stats, wecom, admin):
    api_router.include_router(module.router)
