from fastapi import APIRouter

from app.api.deps import ContainerDep, UserDep
from app.core.errors import NotFound
from app.services.recording_practices import available_scenarios, published_scenarios
from app.services.scenarios import Scenario

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _card(s: Scenario) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "department": s.department,
        "difficulty": s.difficulty,
        "estimated_minutes": s.estimated_minutes,
        "max_turns": s.max_turns,
        "tags": s.tags,
        "summary": s.summary,
        "persona": {"name": s.persona.name, "role": s.persona.role, "personality": s.persona.personality},
    }


@router.get("")
async def list_scenarios(c: ContainerDep, user: UserDep) -> list[dict]:
    async with c.session_factory() as db:
        scenarios = list((await available_scenarios(db, c.scenarios)).values())
    dept = next((d for s in scenarios for d in s.department if d in user.department), None)
    return [_card(s) for s in sorted(scenarios, key=lambda s: bool(dept and dept not in s.department))]


@router.get("/{scenario_id}")
async def get_scenario(scenario_id: str, c: ContainerDep, _: UserDep) -> dict:
    async with c.session_factory() as db:
        entry = (await published_scenarios(db, c.scenarios)).get(scenario_id)
        if entry is None:
            raise NotFound("练习不存在或暂未发布")
        s, rec = entry
    rubric = c.scenarios.rubric_for(s)
    # 只返回给员工看的信息；隐藏需求、异议、阈值不下发
    return {
        **_card(s),
        "source_recording": {"id": rec.id, "title": rec.title or f"录音 #{rec.id}"},
        "background": s.background,
        "goal": s.goal,
        "opening": {"speaker": s.opening.speaker, "tip": s.opening.tip},
        "rubric": {
            "name": rubric.name,
            "dimensions": [{"name": d.name, "weight": d.weight} for d in rubric.dimensions],
        },
    }
