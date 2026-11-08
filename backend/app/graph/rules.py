"""纯规则函数：信任值上下限保护、结束判定、总分计算（不依赖模型，便于单测）。"""

from dataclasses import dataclass

from app.graph.schemas import CoachOutput, DimensionScore, TurnEvaluation
from app.services.scenarios import Rubric, Scenario


@dataclass
class TurnOutcome:
    trust_before: int
    trust_after: int
    delta: int
    resolved: list[str]
    open_objections: list[str]
    status: str


def apply_evaluation(
    scenario: Scenario, trust: int, open_ids: list[str], turn: int, ev: TurnEvaluation
) -> TurnOutcome:
    r = scenario.state_rules
    resolved = [oid for oid in dict.fromkeys(ev.resolved_objection_ids) if oid in open_ids]
    delta = max(-r.max_loss_per_turn, min(r.max_gain_per_turn, ev.trust_delta))
    after = max(0, min(100, trust + delta))
    remaining = [oid for oid in open_ids if oid not in resolved]
    key_open = scenario.key_objection_ids & set(remaining)

    if ev.hangup or after <= r.hangup_threshold:
        status = "hangup"
    elif after >= r.deal_threshold and not key_open and turn >= r.min_turns_to_deal:
        status = "deal"
    elif turn >= scenario.max_turns:
        status = "max_turns"
    else:
        status = "ongoing"
    if status != "deal" and after >= r.deal_threshold:
        # 关键顾虑未化解前，信任值封顶在成交线以下，避免“三句话被说服”
        after = r.deal_threshold - 1
        delta = after - trust
    return TurnOutcome(trust, after, delta, resolved, remaining, status)


def normalize_dimensions(rubric: Rubric, out: CoachOutput) -> list[DimensionScore]:
    """按评分表顺序对齐维度，缺失维度给中间分并注明。"""
    by_name = {d.name: d for d in out.dimension_scores}
    return [
        by_name.get(d.name) or DimensionScore(name=d.name, score=3, comment="（模型未给出该维度评分）")
        for d in rubric.dimensions
    ]


def total_score(rubric: Rubric, dims: list[DimensionScore], hints_used: int) -> int:
    weights = {d.name: d.weight for d in rubric.dimensions}
    raw = sum(d.score / 5 * weights[d.name] for d in dims) / rubric.total_weight * 100
    penalty = min(rubric.hint_penalty * hints_used, rubric.hint_penalty_max)
    return max(0, min(100, round(raw - penalty)))
