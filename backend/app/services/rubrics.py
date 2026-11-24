"""已发布评分标准及版本管理。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.db.models import RubricVersion
from app.services.scenarios import Rubric, ScenarioRegistry


async def versions(db: AsyncSession, rubric_id: str):
    return await db.scalars(
        select(RubricVersion)
        .where(RubricVersion.rubric_id == rubric_id)
        .order_by(RubricVersion.version.desc())
    )


async def current_rubric(db: AsyncSession, registry: ScenarioRegistry, rubric_id: str) -> Rubric:
    row = await db.scalar(
        select(RubricVersion)
        .where(RubricVersion.rubric_id == rubric_id)
        .order_by(RubricVersion.version.desc())
        .limit(1)
    )
    return Rubric.model_validate(row.content) if row else registry.rubrics[rubric_id]


async def publish(db: AsyncSession, rubric: Rubric, base_version: int) -> int:
    version = base_version + 1
    stmt = (
        insert(RubricVersion)
        .values(rubric_id=rubric.id, version=version, content=rubric.model_dump(mode="json"))
        .on_conflict_do_nothing()
        .returning(RubricVersion.version)
    )
    latest = await db.scalar(
        select(RubricVersion.version)
        .where(RubricVersion.rubric_id == rubric.id)
        .order_by(RubricVersion.version.desc())
        .limit(1)
    )
    if (latest or 0) != base_version or await db.scalar(stmt) is None:
        raise Conflict("评分标准已有新版本，请刷新后再发布")
    return version
