"""长期记忆：基于 LangGraph Store 记录员工跨会话的薄弱维度，供教练/提示个性化。"""

from datetime import UTC, datetime

from langgraph.store.base import BaseStore

KEEP_RECENT = 5


def _ns(user_id: str) -> tuple[str, ...]:
    return ("users", user_id, "coach")


async def load_profile(store: BaseStore | None, user_id: str) -> dict:
    if store is None:
        return {}
    item = await store.aget(_ns(user_id), "profile")
    return item.value if item else {}


async def save_practice_result(store: BaseStore | None, user_id: str, scenario_id: str, report: dict) -> None:
    if store is None:
        return
    profile = await load_profile(store, user_id)
    weak = [d["name"] for d in sorted(report.get("dimension_scores", []), key=lambda d: d["score"])[:2]]
    recent = [
        {
            "scenario_id": scenario_id,
            "score": report.get("total_score"),
            "weak": weak,
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        *profile.get("recent", []),
    ][:KEEP_RECENT]
    await store.aput(
        _ns(user_id), "profile", {"recent": recent, "practice_count": profile.get("practice_count", 0) + 1}
    )


def describe_profile(profile: dict) -> str:
    recent = profile.get("recent") or []
    if not recent:
        return "（首次练习，暂无历史）"
    weak: dict[str, int] = {}
    for r in recent:
        for w in r.get("weak", []):
            weak[w] = weak.get(w, 0) + 1
    top = "、".join(k for k, _ in sorted(weak.items(), key=lambda x: -x[1])[:2]) or "无"
    scores = "、".join(str(r.get("score")) for r in recent if r.get("score") is not None)
    return f"累计练习 {profile.get('practice_count', len(recent))} 次；近期得分：{scores}；反复出现的薄弱维度：{top}"
