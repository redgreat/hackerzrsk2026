"""录音派生练习的发布范围与场景读取。"""

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import load_only

from app.core.errors import Conflict, NotFound
from app.db.models import Recording
from app.services.scenarios import Scenario, ScenarioRegistry


class GeneratedPractices(BaseModel):
    scenarios: list[Scenario] = Field(min_length=1, max_length=3)


class PracticeEvidence(BaseModel):
    seqs: list[int] = Field(max_length=6)


def recording_scenarios(recording: Recording) -> dict[str, dict]:
    meta = recording.meta or {}
    archived = set(meta.get("archived_scenario_ids", []))
    entries = {
        sid: {"status": "archived" if sid in archived else "approved"}
        for sid in meta.get("extracted_scenario_ids", [])
    }
    entries.update(meta.get("scenario_drafts", {}))
    return entries


async def published_scenarios(db, registry: ScenarioRegistry) -> dict[str, tuple[Scenario, Recording]]:
    recordings = await db.scalars(
        select(Recording)
        .options(load_only(Recording.meta, Recording.title))
        .where(
            Recording.published.is_(True),
            or_(Recording.meta.has_key("extracted_scenario_ids"), Recording.meta.has_key("scenario_drafts")),
        )
        .order_by(Recording.id)
    )
    scenes = {}
    for rec in recordings:
        for sid, entry in recording_scenarios(rec).items():
            if entry["status"] != "approved":
                continue
            scene = (
                Scenario.model_validate(yaml.safe_load(entry["yaml"]))
                if entry.get("yaml")
                else registry.scenarios.get(sid)
            )
            if scene and scene.enabled:
                scenes.setdefault(sid, (scene, rec))
    return scenes


async def available_scenarios(db, registry: ScenarioRegistry) -> dict[str, Scenario]:
    return {sid: scene for sid, (scene, _) in (await published_scenarios(db, registry)).items()}


async def require_available(db, registry: ScenarioRegistry, sid: str, *, existing: bool = False) -> Scenario:
    scenario = (await available_scenarios(db, registry)).get(sid)
    if scenario is None:
        if existing:
            raise Conflict("该练习已暂停，可结束本次对练并查看报告")
        raise NotFound("练习不存在或暂未发布")
    return scenario
