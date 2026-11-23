"""管理后台接口（只读）。全部要求管理员身份，见 deps.AdminDep。"""

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, ContainerDep
from app.core.errors import NotFound
from app.services import admin as svc
from app.services import settings_store, stats

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


class KnowledgeCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=20000)
    tags: list[str] = Field(default_factory=list)
    scenario_ids: list[str] = Field(default_factory=list)


class KnowledgeImportIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200000)


@router.post("/knowledge")
async def knowledge_create(body: KnowledgeCreateIn, c: ContainerDep, _: AdminDep) -> dict:
    n = await c.knowledge.create_manual(body.title, body.content, body.tags, body.scenario_ids)
    return {"created": n}


@router.post("/knowledge/import")
async def knowledge_import(body: KnowledgeImportIn, c: ContainerDep, _: AdminDep) -> dict:
    """粘贴 Markdown 导入（格式同 knowledge/*.md，按二级标题切块；同名重复导入会整体替换）。"""
    n = await c.knowledge.import_markdown(body.name, body.text)
    return {"imported": n}


@router.delete("/knowledge/{chunk_id}")
async def knowledge_delete(chunk_id: int, c: ContainerDep, _: AdminDep) -> dict:
    if not await c.knowledge.delete(chunk_id):
        raise NotFound("知识片段不存在")
    return {"deleted": True}


@router.post("/knowledge/rebuild")
async def knowledge_rebuild(c: ContainerDep, _: AdminDep) -> dict:
    """重新加载 knowledge/ 目录（服务器上的 Markdown 源）并补算缺失向量。"""
    return await c.knowledge.rebuild()


class SettingIn(BaseModel):
    value: bool | int | float | str


@router.get("/settings")
async def settings_list(c: ContainerDep, _: AdminDep) -> list[dict]:
    return await settings_store.list_items(c.session_factory, c.settings)


@router.put("/settings/{key:path}")
async def settings_save(key: str, body: SettingIn, c: ContainerDep, admin: AdminDep) -> dict:
    value = await settings_store.save(c.session_factory, c.settings, key, body.value, admin.userid)
    return {"key": key, "value": value}


@router.delete("/settings/{key:path}")
async def settings_reset(key: str, c: ContainerDep, admin: AdminDep) -> dict:
    value = await settings_store.reset(c.session_factory, c.settings, key, admin.userid)
    return {"key": key, "value": value}
