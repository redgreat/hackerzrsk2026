"""管理后台接口。全部要求管理员身份，见 deps.AdminDep。"""

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from app.api.deps import AdminDep, ContainerDep
from app.core.errors import Conflict, NotFound
from app.services import admin as svc
from app.services import knowledge_scripts, rubrics, stats
from app.services.scenarios import Dimension, Rubric

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
    result = await svc.list_sessions(c.session_factory, user_id, scenario_id, status, page, size)
    return {**result, "can_clear": c.settings.app_env in ("dev", "test")}


@router.delete("/sessions")
async def clear_sessions(c: ContainerDep, _: AdminDep) -> dict:
    return await svc.clear_training_records(c.session_factory, c.settings.app_env, exams=False)


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
async def knowledge(c: ContainerDep, _: AdminDep) -> list[knowledge_scripts.ScriptRecord]:
    return await knowledge_scripts.list_scripts(c.knowledge)


@router.get("/knowledge/export")
async def export_knowledge(c: ContainerDep, _: AdminDep) -> knowledge_scripts.ScriptBundle:
    return knowledge_scripts.ScriptBundle(scripts=await knowledge_scripts.list_scripts(c.knowledge))


@router.post("/knowledge/import")
async def import_knowledge(body: knowledge_scripts.ScriptBundle, c: ContainerDep, _: AdminDep) -> dict:
    return {"imported": await knowledge_scripts.save_scripts(c.knowledge, body.scripts)}


@router.post("/knowledge")
async def add_knowledge(body: knowledge_scripts.ScriptIn, c: ContainerDep, _: AdminDep) -> dict:
    record = knowledge_scripts.ScriptRecord(id=uuid.uuid4(), **body.model_dump())
    await knowledge_scripts.save_scripts(c.knowledge, [record])
    return {"id": record.id}


@router.put("/knowledge/{script_id}")
async def edit_knowledge(
    script_id: uuid.UUID, body: knowledge_scripts.ScriptIn, c: ContainerDep, _: AdminDep
) -> dict:
    record = knowledge_scripts.ScriptRecord(id=script_id, **body.model_dump())
    await knowledge_scripts.save_scripts(c.knowledge, [record], require_existing=True)
    return {"id": script_id}


class RubricUpdate(BaseModel):
    base_version: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=100)
    dimensions: list[Dimension] = Field(min_length=1, max_length=20)
    hint_penalty: float = Field(ge=0, le=100)
    hint_penalty_max: float = Field(ge=0, le=100)
    red_lines: list[str] = Field(max_length=30)
    red_line_cap: int = Field(ge=0, le=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请填写评分表名称")
        return value.strip()

    @field_validator("dimensions")
    @classmethod
    def clean_dimensions(cls, values: list[Dimension]) -> list[Dimension]:
        for item in values:
            item.name, item.good, item.bad = item.name.strip(), item.good.strip(), item.bad.strip()
        if any(not item.name or not item.good or not item.bad for item in values):
            raise ValueError("每个维度需填写名称、良好表现和较差表现")
        if len({item.name for item in values}) != len(values):
            raise ValueError("维度名称不能重复")
        return values


@router.get("/rubric")
async def rubric_history(c: ContainerDep, _: AdminDep) -> dict:
    rubric_id = c.settings.recordings.rubric_id
    async with c.session_factory() as db:
        history = [
            {"version": row.version, "created_at": row.created_at, "rubric": row.content}
            for row in await rubrics.versions(db, rubric_id)
        ]
        if not history:
            raise Conflict("评分标准尚未初始化，请检查数据库迁移和评分标准配置")
    return {"versions": history}


@router.post("/rubric")
async def publish_rubric(body: RubricUpdate, c: ContainerDep, _: AdminDep) -> dict:
    rubric = Rubric(id=c.settings.recordings.rubric_id, **body.model_dump(exclude={"base_version"}))
    rubric.red_lines = list(dict.fromkeys(line.strip() for line in rubric.red_lines if line.strip()))
    async with c.session_factory() as db, db.begin():
        version = await rubrics.publish(db, rubric, body.base_version)
    return {"version": version}
