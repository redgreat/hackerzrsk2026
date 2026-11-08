"""练习统计：个人成长 + 全员成本/效果（比赛汇报数据来源）。"""

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ModelUsage, PracticeSession, User

FINISHED = PracticeSession.report.is_not(None)


async def my_stats(sf: async_sessionmaker[AsyncSession], user: User) -> dict:
    async with sf() as db:
        rows = (
            (
                await db.execute(
                    select(PracticeSession)
                    .where(PracticeSession.user_id == user.id, FINISHED)
                    .order_by(PracticeSession.started_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
    scores = [s.total_score for s in rows if s.total_score is not None]
    dims: dict[str, list[int]] = {}
    for s in rows:
        for d in s.report.get("dimension_scores", []):
            dims.setdefault(d["name"], []).append(d["score"])
    return {
        "practice_count": len(rows),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "best_score": max(scores, default=None),
        "trend": [
            {"date": s.started_at.isoformat(), "score": s.total_score, "scenario": s.scenario_name}
            for s in reversed(rows[:20])
        ],
        "dimension_avg": sorted(
            ({"name": k, "avg": round(sum(v) / len(v), 2)} for k, v in dims.items()), key=lambda x: x["avg"]
        ),
    }


async def overview(sf: async_sessionmaker[AsyncSession], manual_cost: float) -> dict:
    duration = func.extract("epoch", PracticeSession.ended_at - PracticeSession.started_at)
    async with sf() as db:
        s = (
            await db.execute(
                select(
                    func.count(PracticeSession.id),
                    func.count(func.distinct(PracticeSession.user_id)),
                    func.avg(PracticeSession.total_score),
                    func.avg(cast(PracticeSession.cost_yuan, Float)),
                    func.sum(cast(PracticeSession.cost_yuan, Float)),
                    func.avg(duration),
                    func.avg(PracticeSession.turns),
                    func.sum(case((PracticeSession.status == "deal", 1), else_=0)),
                ).where(FINISHED)
            )
        ).one()
        by_purpose = (
            await db.execute(
                select(
                    ModelUsage.purpose,
                    func.count(),
                    func.sum(ModelUsage.prompt_tokens),
                    func.sum(ModelUsage.completion_tokens),
                    func.sum(cast(ModelUsage.cost_yuan, Float)),
                    func.avg(ModelUsage.latency_ms),
                ).group_by(ModelUsage.purpose)
            )
        ).all()
        by_scenario = (
            await db.execute(
                select(PracticeSession.scenario_name, func.count(), func.avg(PracticeSession.total_score))
                .where(FINISHED)
                .group_by(PracticeSession.scenario_name)
            )
        ).all()
    count, users, avg_score, avg_cost, total_cost, avg_dur, avg_turns, deals = (
        float(v) if v is not None and not isinstance(v, int) else v for v in s
    )
    avg_cost = avg_cost or 0.0
    return {
        "finished_sessions": count,
        "users": users,
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
        "deal_rate": round(deals / count, 3) if count else None,
        "avg_turns": round(avg_turns, 1) if avg_turns is not None else None,
        "avg_duration_seconds": round(avg_dur) if avg_dur is not None else None,
        "avg_cost_yuan": round(avg_cost, 4),
        "total_cost_yuan": round(total_cost or 0, 4),
        "manual_coaching_cost_yuan": manual_cost,
        "cost_saving_ratio": round(1 - avg_cost / manual_cost, 4) if count and manual_cost else None,
        "by_purpose": [
            {
                "purpose": p,
                "calls": c,
                "prompt_tokens": pt or 0,
                "completion_tokens": ct or 0,
                "cost_yuan": round(cost or 0, 4),
                "avg_latency_ms": round(float(lat or 0)),
            }
            for p, c, pt, ct, cost, lat in by_purpose
        ],
        "by_scenario": [
            {"scenario": n, "count": c, "avg_score": round(float(a), 1) if a is not None else None}
            for n, c, a in by_scenario
        ],
    }
