from fastapi import APIRouter

from app.api import (
    accounts,
    admin,
    auth,
    exams,
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
    training_admin,
):
    api_router.include_router(module.router)
