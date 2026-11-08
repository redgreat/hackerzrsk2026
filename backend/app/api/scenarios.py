from fastapi import APIRouter

from app.api.deps import ContainerDep, UserDep
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
    dept = next((d for s in c.scenarios.list() for d in s.department if d in user.department), None)
    return [_card(s) for s in c.scenarios.list(dept)]


@router.get("/{scenario_id}")
async def get_scenario(scenario_id: str, c: ContainerDep, _: UserDep) -> dict:
    s = c.scenarios.get(scenario_id)
    rubric = c.scenarios.rubric_for(s)
    # 只返回给员工看的信息；隐藏需求、异议、阈值不下发
    return {
        **_card(s),
        "background": s.background,
        "goal": s.goal,
        "opening": {"speaker": s.opening.speaker, "tip": s.opening.tip},
        "rubric": {
            "name": rubric.name,
            "dimensions": [{"name": d.name, "weight": d.weight} for d in rubric.dimensions],
        },
    }
