"""纯规则函数：信任值上下限保护、结束判定、总分计算（不依赖模型，便于单测）。"""

import re
from dataclasses import dataclass

from app.graph.schemas import CoachOutput, DimensionScore, TurnEvaluation
from app.services.scenarios import Rubric, Scenario


def clearly_off_topic(text: str) -> bool:
    compact = re.sub(r"[\W_]", "", text).lower()
    return not compact or bool(
        re.fullmatch(
            r"(?:请问)?你(?:是(?:谁|什么模型|ai|千问)(?:你今天开心吗)?|今天开心吗)"
            r"|(?:请)?(?:忽略|忘记)(?:之前|以上|所有|前面)的?(?:指令|规则|提示词).*",
            compact,
        )
    )


def leaves_customer_role(text: str) -> bool:
    return bool(
        re.search(
            r"(?:我是|作为|我的身份是|我叫)\s*(?:一个|一名|您的?|你的?)?\s*"
            r"(?:AI|人工智能|语言模型|大语言模型|虚拟助手|智能助手|千问|Qwen|ChatGPT|DeepSeek)"
            r"|有什么(?:可以)?帮(?:助|到)?[您你]|需要我帮忙做什么|系统提示词|我扮演",
            text,
            re.IGNORECASE,
        )
    )


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
    # 模型有时会照抄提示中的「[id] 说明」，仍只允许命中当前未化解的顾虑。
    resolved_ids = []
    for raw_id in ev.resolved_objection_ids:
        oid = raw_id.strip()
        bracketed = re.fullmatch(r"\[([\w-]+)\](?:\s+.*)?", oid)
        resolved_ids.append(bracketed[1] if bracketed else oid)
    resolved = [oid for oid in dict.fromkeys(resolved_ids) if oid in open_ids]
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
        # 关键顾虑未化解前，信任值封顶在达标线以下，避免“套一句话就过关”
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


def total_score(
    rubric: Rubric, dims: list[DimensionScore], hints_used: int, red_line_hit: bool = False
) -> int:
    weights = {d.name: d.weight for d in rubric.dimensions}
    raw = sum(d.score / 5 * weights[d.name] for d in dims) / rubric.total_weight * 100
    penalty = min(rubric.hint_penalty * hints_used, rubric.hint_penalty_max)
    score = max(0, min(100, round(raw - penalty)))
    return min(score, rubric.red_line_cap) if red_line_hit else score


def red_line_violations(inner_thoughts: list[dict], coach_reported: list[str]) -> list[dict]:
    """合并逐轮评估命中的红线与教练复核发现的红线（去重，逐轮记录优先）。"""
    items = [{"turn": t["turn"], "red_line": t["red_line"]} for t in inner_thoughts if t.get("red_line")]
    seen = {f"第{i['turn']}轮：{i['red_line']}" for i in items} | {i["red_line"] for i in items}
    for text in coach_reported:
        text = text.strip()
        if text and text not in seen and not any(i["red_line"] in text for i in items):
            items.append({"turn": None, "red_line": text})
            seen.add(text)
    return items
