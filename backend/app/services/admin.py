"""管理后台只读查询：用户、练习记录、模型用量、场景与知识库。

对话内容与客户内心独白仅向管理员开放；接口层统一经过 AdminDep 鉴权。
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import KnowledgeChunk, ModelUsage, PracticeMessage, PracticeSession, User
from app.services.scenarios import ScenarioRegistry


def _page(page: int, size: int) -> tuple[int, int]:
    size = max(1, min(size, 100))
    return (max(page, 1) - 1) * size, size


async def list_users(sf: async_sessionmaker[AsyncSession], q: str | None, page: int, size: int) -> dict:
    offset, size = _page(page, size)
    cond = []
    if q:
        cond.append(User.userid.ilike(f"%{q}%") | User.name.ilike(f"%{q}%") | User.department.ilike(f"%{q}%"))
    stats = (
        select(
            PracticeSession.user_id,
            func.count(PracticeSession.id).label("sessions"),
            func.avg(PracticeSession.total_score).label("avg_score"),
            func.sum(PracticeSession.cost_yuan).label("cost"),
            func.max(PracticeSession.started_at).label("last_at"),
        )
        .group_by(PracticeSession.user_id)
        .subquery()
    )
    base = (
        select(User, stats.c.sessions, stats.c.avg_score, stats.c.cost, stats.c.last_at)
        .outerjoin(stats, stats.c.user_id == User.id)
        .where(*cond)
    )
    async with sf() as db:
        total = (await db.execute(select(func.count()).select_from(User).where(*cond))).scalar_one()
        rows = (
            await db.execute(base.order_by(User.last_login_at.desc().nulls_last()).offset(offset).limit(size))
        ).all()
    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "userid": u.userid,
                "name": u.name,
                "department": u.department,
                "source": u.source,
                "last_login_at": _iso(u.last_login_at),
                "sessions": s or 0,
                "avg_score": round(float(a), 1) if a is not None else None,
                "cost_yuan": round(float(c or 0), 4),
                "last_practice_at": _iso(last),
            }
            for u, s, a, c, last in rows
        ],
    }


async def list_sessions(
    sf: async_sessionmaker[AsyncSession],
    user_id: int | None,
    scenario_id: str | None,
    status: str | None,
    page: int,
    size: int,
) -> dict:
    offset, size = _page(page, size)
    cond = []
    if user_id:
        cond.append(PracticeSession.user_id == user_id)
    if scenario_id:
        cond.append(PracticeSession.scenario_id == scenario_id)
    if status:
        cond.append(PracticeSession.status == status)
    async with sf() as db:
        total = (
            await db.execute(select(func.count()).select_from(PracticeSession).where(*cond))
        ).scalar_one()
        rows = (
            await db.execute(
                select(PracticeSession, User)
                .join(User, User.id == PracticeSession.user_id)
                .where(*cond)
                .order_by(PracticeSession.started_at.desc())
                .offset(offset)
                .limit(size)
            )
        ).all()
    return {
        "total": total,
        "items": [
            {**_session_row(s), "userid": u.userid, "user_name": u.name, "department": u.department}
            for s, u in rows
        ],
    }


def _session_row(s: PracticeSession) -> dict:
    return {
        "id": str(s.id),
        "scenario_id": s.scenario_id,
        "scenario_name": s.scenario_name,
        "status": s.status,
        "turns": s.turns,
        "hints_used": s.hints_used,
        "total_score": s.total_score,
        "final_trust": s.final_trust,
        "prompt_tokens": s.prompt_tokens,
        "completion_tokens": s.completion_tokens,
        "cost_yuan": round(float(s.cost_yuan or 0), 4),
        "started_at": _iso(s.started_at),
        "ended_at": _iso(s.ended_at),
    }


async def session_detail(sf: async_sessionmaker[AsyncSession], sid: uuid.UUID) -> dict | None:
    async with sf() as db:
        row = (
            await db.execute(
                select(PracticeSession, User)
                .join(User, User.id == PracticeSession.user_id)
                .where(PracticeSession.id == sid)
            )
        ).first()
        if row is None:
            return None
        s, u = row
        msgs = (
            (
                await db.execute(
                    select(PracticeMessage)
                    .where(PracticeMessage.session_id == sid)
                    .order_by(PracticeMessage.seq)
                )
            )
            .scalars()
            .all()
        )
        usage = (
            (await db.execute(select(ModelUsage).where(ModelUsage.session_id == sid).order_by(ModelUsage.id)))
            .scalars()
            .all()
        )
    return {
        **_session_row(s),
        "user": {"id": u.id, "userid": u.userid, "name": u.name, "department": u.department},
        "report": s.report,
        "messages": [
            {
                "seq": m.seq,
                "turn": m.turn,
                "role": m.role,
                "content": m.content,
                "trust_delta": m.trust_delta,
                "trust_after": m.trust_after,
                "inner_thought": m.inner_thought,
                "meta": m.meta,
            }
            for m in msgs
        ],
        "usage": [
            {
                "purpose": r.purpose,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_yuan": float(r.cost_yuan),
                "latency_ms": r.latency_ms,
            }
            for r in usage
        ],
    }


async def list_usage(sf: async_sessionmaker[AsyncSession], purpose: str | None, page: int, size: int) -> dict:
    offset, size = _page(page, size)
    cond = [ModelUsage.purpose == purpose] if purpose else []
    async with sf() as db:
        total = (await db.execute(select(func.count()).select_from(ModelUsage).where(*cond))).scalar_one()
        rows = (
            (
                await db.execute(
                    select(ModelUsage).where(*cond).order_by(ModelUsage.id.desc()).offset(offset).limit(size)
                )
            )
            .scalars()
            .all()
        )
        by_day = (
            await db.execute(
                select(
                    func.date_trunc("day", ModelUsage.created_at).label("day"),
                    func.count().label("calls"),
                    func.sum(cast(ModelUsage.cost_yuan, Float)).label("cost"),
                    func.sum(ModelUsage.prompt_tokens + ModelUsage.completion_tokens).label("tokens"),
                )
                .where(ModelUsage.created_at >= datetime.now(UTC) - timedelta(days=30))
                .group_by("day")
                .order_by("day")
            )
        ).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "session_id": str(r.session_id) if r.session_id else None,
                "user_id": r.user_id,
                "purpose": r.purpose,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "audio_seconds": float(r.audio_seconds),
                "tts_chars": r.tts_chars,
                "cost_yuan": float(r.cost_yuan),
                "latency_ms": r.latency_ms,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ],
        "daily": [
            {"day": _iso(d), "calls": c, "cost_yuan": round(float(cost or 0), 4), "tokens": int(t or 0)}
            for d, c, cost, t in by_day
        ],
    }


async def trend(sf: async_sessionmaker[AsyncSession], days: int) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
    async with sf() as db:
        rows = (
            await db.execute(
                select(
                    func.date_trunc("day", PracticeSession.started_at).label("day"),
                    func.count().label("sessions"),
                    func.avg(PracticeSession.total_score).label("avg_score"),
                    func.sum(cast(PracticeSession.cost_yuan, Float)).label("cost"),
                )
                .where(PracticeSession.started_at >= since)
                .group_by("day")
                .order_by("day")
            )
        ).all()
    return [
        {
            "day": _iso(d),
            "sessions": n,
            "avg_score": round(float(a), 1) if a is not None else None,
            "cost_yuan": round(float(c or 0), 4),
        }
        for d, n, a, c in rows
    ]


def scenarios_admin(registry: ScenarioRegistry) -> list[dict]:
    out = []
    for s in registry.list():
        rubric = registry.rubric_for(s)
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "department": s.department,
                "difficulty": s.difficulty,
                "max_turns": s.max_turns,
                "summary": s.summary,
                "goal": s.goal,
                "background": s.background,
                "persona": s.persona.model_dump(),
                "state_rules": s.state_rules.model_dump(),
                "scoring": s.scoring,
                "rubric": {"name": rubric.name, "dimensions": [d.model_dump() for d in rubric.dimensions]},
            }
        )
    return out


async def list_knowledge(sf: async_sessionmaker[AsyncSession]) -> list[dict]:
    async with sf() as db:
        rows = (
            await db.execute(
                select(
                    KnowledgeChunk.id,
                    KnowledgeChunk.source,
                    KnowledgeChunk.title,
                    KnowledgeChunk.tags,
                    KnowledgeChunk.scenario_ids,
                    KnowledgeChunk.embedding.is_not(None),
                    KnowledgeChunk.content,
                ).order_by(KnowledgeChunk.id)
            )
        ).all()
    return [
        {
            "id": i,
            "source": src,
            "title": t,
            "tags": tags,
            "scenario_ids": sids,
            "has_embedding": emb,
            "preview": content[:120],
        }
        for i, src, t, tags, sids, emb, content in rows
    ]


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None
