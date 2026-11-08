from fastapi import APIRouter

from app.api import auth, scenarios, sessions, speech, stats, system

api_router = APIRouter(prefix="/api")
for module in (system, auth, scenarios, sessions, speech, stats):
    api_router.include_router(module.router)
