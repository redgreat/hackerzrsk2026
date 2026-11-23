from fastapi import APIRouter

from app.api import (
    accounts,
    admin,
    auth,
    exams,
    knowledge_events,
    recordings,
    scenarios,
    sessions,
    speech,
    stats,
    system,
    training_admin,
    wecom,
)

api_router = APIRouter(prefix="/api")
for module in (
    system,
    auth,
    scenarios,
    sessions,
    speech,
    stats,
    wecom,
    admin,
    accounts,
    recordings,
    exams,
    knowledge_events,
    training_admin,
):
    api_router.include_router(module.router)
