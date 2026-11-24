"""管理话术原稿，事务内同步供教练检索的片段。"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import NotFound
from app.db.models import KnowledgeScript
from app.services.guard import mask_pii
from app.services.knowledge import KnowledgeBase, ParsedChunk

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
ScenarioId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class ScriptIn(BaseModel):
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
    enabled: bool = True
    tags: list[Tag] = Field(default_factory=list, max_length=30)
    scenario_ids: list[ScenarioId] = Field(default_factory=list, max_length=50)

    @field_validator("title", "content", "category")
    @classmethod
    def redact(cls, value: str) -> str:
        return mask_pii(value)


class ScriptRecord(ScriptIn):
    id: uuid.UUID


class ScriptBundle(BaseModel):
    version: Literal[1] = 1
    scripts: list[ScriptRecord]


async def list_scripts(kb: KnowledgeBase) -> list[ScriptRecord]:
    async with kb.session_factory() as db:
        rows = await db.scalars(
            select(KnowledgeScript).order_by(KnowledgeScript.category, KnowledgeScript.title)
        )
        return [ScriptRecord.model_validate(row, from_attributes=True) for row in rows]


async def save_scripts(
    kb: KnowledgeBase, records: list[ScriptRecord], *, require_existing: bool = False
) -> int:
    # 按主键稳定排序，避免批量导入和单条编辑交叉锁定。
    unique = {record.id: record for record in records}
    ordered = sorted(unique.values(), key=lambda record: record.id)
    sources = {f"script:{record.id}" for record in ordered}
    chunks = [
        ParsedChunk(f"script:{record.id}", record.title, record.content, record.tags, record.scenario_ids)
        for record in ordered
        if record.enabled
    ]
    async with kb.session_factory() as db, db.begin():
        for record in ordered:
            values = record.model_dump(exclude={"id"})
            if require_existing:
                row = await db.get(KnowledgeScript, record.id, with_for_update=True)
                if row is None:
                    raise NotFound("话术不存在")
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                stmt = insert(KnowledgeScript).values(id=record.id, **values)
                await db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=values))
        # 管理话术用关键词检索，导入和发布无需依赖外部向量服务。
        await kb.write_chunks(db, chunks, [None] * len(chunks), sources)
    return len(ordered)
