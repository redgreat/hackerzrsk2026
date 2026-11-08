"""管理后台接口（只读）。全部要求管理员身份，见 deps.AdminDep。"""

import uuid

from fastapi import APIRouter, Query

from app.api.deps import AdminDep, ContainerDep
from app.core.errors import NotFound
from app.services import admin as svc
from app.services import stats

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
async def overview(c: ContainerDep, _: AdminDep) -> dict:
    return await stats.overview(c.session_factory, c.settings.manual_coaching_cost_yuan)


@router.get("/trend")
async def trend(c: ContainerDep, _: AdminDep, days: int = Query(30, ge=1, le=365)) -> list[dict]:
    return await svc.trend(c.session_factory, days)


@router.get("/users")
async def users(c: ContainerDep, _: AdminDep, q: str | None = None, page: int = 1, size: int = 20) -> dict:
    return await svc.list_users(c.session_factory, q, page, size)


@router.get("/sessions")
async def sessions(
    c: ContainerDep,
    _: AdminDep,
    user_id: int | None = None,
    scenario_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    return await svc.list_sessions(c.session_factory, user_id, scenario_id, status, page, size)


@router.get("/sessions/{sid}")
async def session_detail(sid: uuid.UUID, c: ContainerDep, _: AdminDep) -> dict:
    detail = await svc.session_detail(c.session_factory, sid)
    if detail is None:
        raise NotFound("练习记录不存在")
    return detail


@router.get("/usage")
async def usage(
    c: ContainerDep, _: AdminDep, purpose: str | None = None, page: int = 1, size: int = 50
) -> dict:
    return await svc.list_usage(c.session_factory, purpose, page, size)


@router.get("/scenarios")
async def scenarios(c: ContainerDep, _: AdminDep) -> list[dict]:
    return svc.scenarios_admin(c.scenarios)


@router.get("/knowledge")
async def knowledge(c: ContainerDep, _: AdminDep) -> list[dict]:
    return await svc.list_knowledge(c.session_factory)
