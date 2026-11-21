"""考试判分纯规则（不依赖数据库，便于单测）。

- 单选/判断：全对 1 分，否则 0 分
- 多选：全对 1 分；只漏选不错选 0.5 分；有错选 0 分
- 各 section 折算百分制后按 weight 加权，得到总分（四舍五入取整）
- 对练 section 取各场景教练报告总分的平均，未完成计 0 分
"""


def question_credit(qtype: str, answer: list[int], chosen: list[int] | None) -> float:
    chosen_set, answer_set = set(chosen or []), set(answer)
    if not chosen_set:
        return 0.0
    if qtype != "multi":
        return 1.0 if chosen_set == answer_set and len(chosen_set) == 1 else 0.0
    if chosen_set == answer_set:
        return 1.0
    return 0.5 if chosen_set < answer_set else 0.0


def grade(
    sections: list[dict], answers: dict[str, list[int]], roleplay_scores: dict[str, int | None]
) -> dict:
    """sections 为出题快照；roleplay_scores：{item key: 报告总分或 None（未完成）}。"""
    out_sections, weighted, total_weight = [], 0.0, 0.0
    for sec in sections:
        items = []
        if sec["type"] == "roleplay":
            for it in sec["items"]:
                s = roleplay_scores.get(it["key"])
                items.append({"key": it["key"], "score": s, "credit": (s or 0) / 100})
        else:
            for it in sec["items"]:
                credit = question_credit(it["type"], it["answer"], answers.get(it["key"]))
                items.append({"key": it["key"], "credit": credit, "correct": credit == 1.0})
        score = round(sum(i["credit"] for i in items) / len(items) * 100, 1) if items else 0.0
        out_sections.append(
            {
                "title": sec["title"],
                "type": sec["type"],
                "weight": sec["weight"],
                "score": score,
                "items": items,
            }
        )
        weighted += score * sec["weight"]
        total_weight += sec["weight"]
    total = round(weighted / total_weight) if total_weight else 0
    return {"total": total, "sections": out_sections}
