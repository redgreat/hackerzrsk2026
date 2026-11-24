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


def recording_scenarios(recording: Recording) -> dict[str, dict]:
    meta = recording.meta or {}
    archived = set(meta.get("archived_scenario_ids", []))
    entries = {
        sid: {"status": "archived" if sid in archived else "approved"}
        for sid in meta.get("extracted_scenario_ids", [])
    }
    entries.update(meta.get("scenario_drafts", {}))
    return entries


async def available_scenarios(db, registry: ScenarioRegistry) -> dict[str, Scenario]:
    recordings = await db.scalars(
        select(Recording)
        .options(load_only(Recording.meta, Recording.published))
        .where(
            or_(Recording.meta.has_key("extracted_scenario_ids"), Recording.meta.has_key("scenario_drafts"))
        )
    )
    scenes = {scenario.id: scenario for scenario in registry.list()}
    unavailable = set()
    for rec in recordings:
        for sid, entry in recording_scenarios(rec).items():
            if not rec.published or entry["status"] != "approved":
                unavailable.add(sid)
            elif entry.get("yaml"):
                scenes[sid] = Scenario.model_validate(yaml.safe_load(entry["yaml"]))
    return {sid: scene for sid, scene in scenes.items() if sid not in unavailable}


async def require_available(db, registry: ScenarioRegistry, sid: str, *, existing: bool = False) -> Scenario:
    scenario = (await available_scenarios(db, registry)).get(sid)
    if scenario is None:
        if existing:
            raise Conflict("该练习已暂停，可结束本次对练并查看报告")
        raise NotFound("练习不存在或暂未发布")
    return scenario
