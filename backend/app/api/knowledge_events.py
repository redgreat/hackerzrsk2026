"""知识案例管理，仅管理员访问完整转写和审核接口。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminDep, ContainerDep
from app.services import knowledge_review as svc

router = APIRouter(prefix="/admin/knowledge-events", tags=["admin-knowledge-events"])


@router.get("")
async def events(
    c: ContainerDep,
    _: AdminDep,
    status: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return await svc.list_events(c.session_factory, status, page, size)


@router.get("/{eid}")
async def detail(eid: int, c: ContainerDep, _: AdminDep) -> dict:
    return await svc.get_event(c.session_factory, eid)


@router.post("/{eid}/review")
async def review(eid: int, body: svc.ReviewIn, c: ContainerDep, user: AdminDep) -> dict:
    return await svc.review_event(c.session_factory, eid, user.id, body)
