"""考试与自测：数据库题库、试卷模板 YAML、出题快照、作答保存、交卷判分。

试卷由 section 组成：quiz（题库选择题）/ listening（听录音答题）/ roleplay（AI 情景对练，禁用提示）。
出题时生成快照（含答案）存入 exam_attempts.sections，作答期间只下发不含答案的视图。
"""

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.db.models import ExamAttempt, ExamPublication, ExamQuestion, PracticeSession, User
from app.services import exam_rules
from app.services.exam_question_bank import ExamQuestionBank
from app.services.practice import PracticeService
from app.services.recording_practices import available_scenarios, require_available
from app.services.recordings import RecordingService
from app.services.rubrics import current_rubric
from app.services.scenarios import ScenarioRegistry

logger = logging.getLogger(__name__)


class Section(BaseModel):
    type: Literal["quiz", "listening", "roleplay"]
    title: str
    weight: float = Field(gt=0)
    count: int | None = Field(None, ge=1)
    # roleplay：指定场景；设置 count 时从中随机抽取
    scenario_ids: list[str] = Field(default_factory=list)
    from_recordings: bool = False


class Paper(BaseModel):
    id: str
    name: str
    kind: Literal["exam", "self_test"] = "exam"
    description: str = ""
    department: list[str] = Field(default_factory=list)
    pass_score: int = Field(60, ge=0, le=100)
    time_limit_minutes: int | None = Field(None, ge=1)
    max_attempts: int | None = Field(None, ge=1)
    show_answers: bool = True
    shuffle: bool = True
    sections: list[Section]
    enabled: bool = True


class ExamRegistry:
    def __init__(self, papers: dict[str, Paper]):
        self.papers = papers

    @classmethod
    def load(cls, root: Path, scenarios: ScenarioRegistry) -> "ExamRegistry":
        papers: dict[str, Paper] = {}
        for f in sorted((root / "papers").glob("*.y*ml")):
            p = Paper.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
            if p.id in papers:
                raise ValueError(f"试卷 id 重复：{p.id}")
            for s in p.sections:
                missing = [sid for sid in s.scenario_ids if sid not in scenarios.scenarios]
                if missing:
                    raise ValueError(f"试卷 {p.id} 引用了不存在的场景：{missing}")
                if s.type == "roleplay" and not (s.scenario_ids or s.from_recordings):
                    raise ValueError(f"试卷 {p.id} 的 {s.title} 未指定场景")
            papers[p.id] = p
        return cls(papers)

    def enabled(self) -> list[Paper]:
        return [p for p in self.papers.values() if p.enabled]

    def get(self, paper_id: str) -> Paper:
        p = self.papers.get(paper_id)
        if not p or not p.enabled:
            raise NotFound(f"试卷不存在：{paper_id}")
        return p


def _now() -> datetime:
    return datetime.now(UTC)


class ExamService:
    def __init__(
        self,
        registry: ExamRegistry,
        sf: async_sessionmaker[AsyncSession],
        practice: PracticeService,
        recordings: RecordingService,
        scenarios: ScenarioRegistry,
    ):
        self.registry = registry
        self.sf = sf
        self.practice = practice
        self.recordings = recordings
        self.scenarios = scenarios
        self.question_bank = ExamQuestionBank(sf, scenarios, recordings.llm)

    # ---------- 出题 ----------

    async def _build_sections(self, db: AsyncSession, paper: Paper, available: dict) -> list[dict]:
        sections = []
        used_questions: set[int] = set()
        used_roleplays: set[str] = set()
        rubrics = {}
        for s in paper.sections:
            items: list[dict] = []
            if s.type == "quiz":
                pool = (
                    await db.scalars(
                        select(ExamQuestion).where(
                            ExamQuestion.status == "approved",
                            ExamQuestion.scenario_id.in_(available),
                            ExamQuestion.id.not_in(used_questions),
                        )
                    )
                ).all()
                count = s.count or len(pool)
                if count == 0 or len(pool) < count:
                    raise Conflict(
                        f"可用合规题不足（当前 {len(pool)} 道，需要 {s.count or 1} 道），请联系管理员补充题库"
                    )
                for q in random.sample(list(pool), count):
                    used_questions.add(q.id)
                    items.append({"key": f"q:{q.id}", **q.content})
            elif s.type == "listening":
                for q in await self.recordings.sample_questions(s.count or 3):
                    items.append(
                        {
                            "key": f"r:{q['id']}",
                            "type": q["type"],
                            "stem": q["stem"],
                            "options": q["options"],
                            "answer": q["answer"],
                            "explanation": q["explanation"],
                            "recording": q["recording"],
                        }
                    )
            else:
                candidates = {sid: self.scenarios.get(sid) for sid in s.scenario_ids}
                if s.from_recordings:
                    candidates = {
                        sid: available[sid]
                        for sid in sorted(available)
                        if sid not in self.scenarios.scenarios and sid not in used_roleplays
                    }
                    if len(candidates) < (s.count or 1):
                        raise AppError("可用的已发布录音练习不足，无法组卷")
                ids = (
                    random.sample(list(candidates), s.count)
                    if s.count and len(candidates) > s.count
                    else candidates
                )
                for sid in ids:
                    used_roleplays.add(sid)
                    sc = candidates[sid]
                    if sc.scoring not in rubrics:
                        rubrics[sc.scoring] = await current_rubric(db, self.scenarios, sc.scoring)
                    items.append(
                        {
                            "key": f"s:{sid}",
                            "scenario_id": sid,
                            "scenario_name": sc.name,
                            "session_id": None,
                            "scenario_snapshot": self.scenarios.snapshot(sc, rubrics[sc.scoring]),
                        }
                    )
            if paper.shuffle and s.type != "roleplay":
                random.shuffle(items)
            if items:  # 例如尚无已审核的录音题目时，跳过该部分
                sections.append({"type": s.type, "title": s.title, "weight": s.weight, "items": items})
        if not sections:
            raise AppError("试卷暂无可用题目，请联系管理员")
        return sections

    async def _attempt_paper(self, db: AsyncSession, attempt: ExamAttempt) -> Paper | None:
        if attempt.paper_snapshot is not None:
            return Paper.model_validate(attempt.paper_snapshot)
        if attempt.publication_id is not None:
            publication = await db.get(ExamPublication, attempt.publication_id)
            return Paper.model_validate(publication.paper)
        return self.registry.papers.get(attempt.paper_id)

    async def admin_papers(self) -> list[dict]:
        return [{**paper_card(p), "enabled": p.enabled} for p in self.registry.papers.values()]

    async def _count_attempts(self, db: AsyncSession, user: User, paper_id: str) -> int:
        return (
            await db.execute(
                select(func.count()).where(ExamAttempt.user_id == user.id, ExamAttempt.paper_id == paper_id)
            )
        ).scalar_one()

    async def start(self, user: User, paper_id: str) -> dict:
        async with self.sf() as db, db.begin():
            # 同一员工重复开考时复用未交卷的记录。
            await db.get(User, user.id, with_for_update=True)
            ongoing = (
                (
                    await db.execute(
                        select(ExamAttempt.id).where(
                            ExamAttempt.user_id == user.id,
                            ExamAttempt.paper_id == paper_id,
                            ExamAttempt.status == "in_progress",
                        )
                    )
                )
                .scalars()
                .first()
            )
            if ongoing is None:
                paper = self.registry.get(paper_id)
                if (
                    paper.kind == "exam"
                    and paper.max_attempts
                    and await self._count_attempts(db, user, paper_id) >= paper.max_attempts
                ):
                    raise Forbidden(f"该考试最多可参加 {paper.max_attempts} 次，您已用完")
                available = await available_scenarios(db, self.scenarios)
                sections = await self._build_sections(db, paper, available)
                if any(
                    item["scenario_id"] not in available
                    for section in sections
                    if section["type"] == "roleplay"
                    for item in section["items"]
                ):
                    raise Conflict("试卷含尚未发布的练习，请联系管理员")
                now = _now()
                ongoing = uuid.uuid4()
                db.add(
                    ExamAttempt(
                        id=ongoing,
                        user_id=user.id,
                        paper_id=paper.id,
                        paper_name=paper.name,
                        paper_snapshot=paper.model_dump(mode="json"),
                        kind=paper.kind,
                        sections=sections,
                        answers={},
                        started_at=now,
                        deadline_at=now + timedelta(minutes=paper.time_limit_minutes)
                        if paper.time_limit_minutes
                        else None,
                    )
                )
        return await self.view(ongoing, user)

    # ---------- 作答 ----------

    async def _owned(self, db: AsyncSession, aid: uuid.UUID, user: User, lock: bool = False) -> ExamAttempt:
        a = await db.get(ExamAttempt, aid, with_for_update=lock)
        if a is None:
            raise NotFound("作答记录不存在")
        if a.user_id != user.id:
            raise Forbidden("无权访问该作答记录")
        return a

    @staticmethod
    def _expired(a: ExamAttempt) -> bool:
        return a.deadline_at is not None and _now() >= a.deadline_at

    async def save_answers(self, aid: uuid.UUID, user: User, answers: dict[str, list[int]]) -> dict:
        async with self.sf() as db, db.begin():
            a = await self._owned(db, aid, user, lock=True)
            if a.status != "in_progress":
                raise Conflict("已交卷，不能再修改答案")
            if self._expired(a):
                raise Conflict("考试时间已到")
            valid = {it["key"]: it for s in a.sections if s["type"] != "roleplay" for it in s["items"]}
            merged = dict(a.answers or {})
            for k, v in answers.items():
                it = valid.get(k)
                if it is None:
                    continue
                v = sorted({i for i in v if 0 <= i < len(it["options"])})
                merged[k] = v if it["type"] == "multi" else v[:1]
            a.answers = merged
        return {"saved": len(merged)}

    async def start_roleplay(self, aid: uuid.UUID, user: User, key: str) -> dict:
        async with self.sf() as db, db.begin():
            a = await self._owned(db, aid, user, lock=True)
            if a.status != "in_progress" or self._expired(a):
                raise Conflict("考试已结束")
            item = next(
                (it for s in a.sections if s["type"] == "roleplay" for it in s["items"] if it["key"] == key),
                None,
            )
            if item is None:
                raise NotFound("对练题不存在")
            await require_available(db, self.scenarios, item["scenario_id"])
            if item.get("session_id"):
                return {"session_id": item["session_id"]}
            mode = "exam" if a.kind == "exam" else "practice"
            session = await self.practice.start(
                user,
                item["scenario_id"],
                mode=mode,
                exam_attempt_id=aid,
                scenario_snapshot=item.get("scenario_snapshot"),
            )
            sections = [
                {
                    **s,
                    "items": [
                        {**it, "session_id": session["id"]} if it["key"] == key else it for it in s["items"]
                    ],
                }
                for s in a.sections
            ]
            a.sections = sections
        return {"session_id": session["id"]}

    async def _roleplay_scores(self, db: AsyncSession, a: ExamAttempt) -> dict[str, PracticeSession | None]:
        out = {}
        for s in a.sections:
            if s["type"] != "roleplay":
                continue
            for it in s["items"]:
                sid = it.get("session_id")
                out[it["key"]] = await db.get(PracticeSession, uuid.UUID(sid)) if sid else None
        return out

    async def submit(self, aid: uuid.UUID, user: User) -> dict:
        async with self.sf() as db, db.begin():
            a = await self._owned(db, aid, user, lock=True)
            if a.status == "in_progress":
                scores = {}
                for key, sess in (await self._roleplay_scores(db, a)).items():
                    if sess is None:
                        scores[key] = None
                        continue
                    try:
                        report = sess.report or await self.practice.end(sess.id, user)
                    except Conflict as exc:
                        raise Conflict("对练报告正在生成，请稍后再交卷") from exc
                    scores[key] = report["total_score"]
                result = exam_rules.grade(a.sections, a.answers or {}, scores)
                paper = await self._attempt_paper(db, a)
                a.result = result
                a.score = result["total"]
                a.passed = result["total"] >= (paper.pass_score if paper else 60)
                a.status = "submitted"
                a.submitted_at = _now()
        return await self.view(aid, user)

    # ---------- 查询 ----------

    async def view(self, aid: uuid.UUID, user: User) -> dict:
        async with self.sf() as db:
            a = await self._owned(db, aid, user)
            expired = a.status == "in_progress" and self._expired(a)
        if expired:
            # 超时自动交卷（按已保存答案判分）
            return await self.submit(aid, user)
        async with self.sf() as db:
            a = await self._owned(db, aid, user)
            sessions = await self._roleplay_scores(db, a)
            paper = await self._attempt_paper(db, a)
        return attempt_view(a, paper, sessions)

    async def list_papers(self, user: User) -> list[dict]:
        async with self.sf() as db:
            papers = self.registry.enabled()
            rows = (
                await db.execute(
                    select(
                        ExamAttempt.paper_id,
                        func.count(),
                        func.max(ExamAttempt.score),
                        func.bool_or(ExamAttempt.passed),
                    )
                    .where(ExamAttempt.user_id == user.id)
                    .group_by(ExamAttempt.paper_id)
                )
            ).all()
            ongoing = dict(
                (
                    await db.execute(
                        select(ExamAttempt.paper_id, ExamAttempt.id).where(
                            ExamAttempt.user_id == user.id, ExamAttempt.status == "in_progress"
                        )
                    )
                ).all()
            )
        stats = {r[0]: r for r in rows}
        dept = user.department or ""
        papers.sort(key=lambda p: (p.kind != "exam", bool(p.department) and dept not in p.department))
        return [
            {
                **paper_card(p),
                "attempts": stats[p.id][1] if p.id in stats else 0,
                "best_score": stats[p.id][2] if p.id in stats else None,
                "passed": bool(stats[p.id][3]) if p.id in stats else False,
                "ongoing_attempt_id": str(ongoing[p.id]) if p.id in ongoing else None,
            }
            for p in papers
        ]

    async def my_attempts(self, user: User, limit: int = 30) -> list[dict]:
        async with self.sf() as db:
            rows = (
                (
                    await db.execute(
                        select(ExamAttempt)
                        .where(ExamAttempt.user_id == user.id)
                        .order_by(ExamAttempt.started_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [attempt_summary(a) for a in rows]

    # ---------- 管理员 ----------

    async def admin_list(self, paper_id: str | None, user_id: int | None, page: int, size: int) -> dict:
        cond = []
        if paper_id:
            cond.append(ExamAttempt.paper_id == paper_id)
        if user_id:
            cond.append(ExamAttempt.user_id == user_id)
        size = max(1, min(size, 100))
        async with self.sf() as db:
            total = (
                await db.execute(select(func.count()).select_from(ExamAttempt).where(*cond))
            ).scalar_one()
            rows = (
                await db.execute(
                    select(ExamAttempt, User)
                    .join(User, User.id == ExamAttempt.user_id)
                    .where(*cond)
                    .order_by(ExamAttempt.started_at.desc())
                    .offset((max(page, 1) - 1) * size)
                    .limit(size)
                )
            ).all()
        return {
            "total": total,
            "items": [
                {
                    **attempt_summary(a),
                    "user": {"id": u.id, "userid": u.userid, "name": u.name, "department": u.department},
                }
                for a, u in rows
            ],
        }

    async def admin_detail(self, aid: uuid.UUID) -> dict:
        async with self.sf() as db:
            a = await db.get(ExamAttempt, aid)
            if a is None:
                raise NotFound("作答记录不存在")
            u = await db.get(User, a.user_id)
            sessions = await self._roleplay_scores(db, a)
            paper = await self._attempt_paper(db, a)
        view = attempt_view(a, paper, sessions, reveal=True)
        return {**view, "user": {"id": u.id, "userid": u.userid, "name": u.name, "department": u.department}}


def paper_card(p: Paper) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "description": p.description,
        "pass_score": p.pass_score,
        "time_limit_minutes": p.time_limit_minutes,
        "max_attempts": p.max_attempts,
        "sections": [{"type": s.type, "title": s.title, "weight": s.weight} for s in p.sections],
    }


def attempt_summary(a: ExamAttempt) -> dict:
    return {
        "id": str(a.id),
        "paper_id": a.paper_id,
        "paper_name": a.paper_name,
        "kind": a.kind,
        "status": a.status,
        "score": a.score,
        "passed": a.passed,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "deadline_at": a.deadline_at.isoformat() if a.deadline_at else None,
        "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
    }


def attempt_view(
    a: ExamAttempt, paper: Paper | None, sessions: dict[str, PracticeSession | None], reveal: bool = False
) -> dict:
    submitted = a.status == "submitted"
    reveal = reveal or (submitted and (a.kind == "self_test" or (paper.show_answers if paper else False)))
    graded = {it["key"]: it for s in (a.result or {}).get("sections", []) for it in s["items"]}
    sections = []
    for s in a.sections:
        items = []
        for it in s["items"]:
            if s["type"] == "roleplay":
                sess = sessions.get(it["key"])
                items.append(
                    {
                        "key": it["key"],
                        "scenario_id": it["scenario_id"],
                        "scenario_name": it["scenario_name"],
                        "session_id": it.get("session_id"),
                        "session_status": sess.status if sess else None,
                        "report_ready": bool(sess and sess.report),
                        "score": sess.total_score if sess and sess.report else None,
                    }
                )
                continue
            view = {k: it[k] for k in ("key", "type", "stem", "options")}
            if "recording" in it:
                view["recording"] = it["recording"]
            view["chosen"] = (a.answers or {}).get(it["key"], [])
            if reveal:
                g = graded.get(it["key"], {})
                view.update(
                    answer=it["answer"], explanation=it.get("explanation", ""), credit=g.get("credit")
                )
            items.append(view)
        sections.append({"type": s["type"], "title": s["title"], "weight": s["weight"], "items": items})
    result = None
    if a.result:
        result = {
            "total": a.result["total"],
            "sections": [
                {k: s[k] for k in ("title", "type", "weight", "score")} for s in a.result["sections"]
            ],
        }
    return {
        **attempt_summary(a),
        "pass_score": paper.pass_score if paper else None,
        "time_limit_minutes": paper.time_limit_minutes if paper else None,
        "server_time": _now().isoformat(),
        "revealed": reveal,
        "result": result,
        "sections": sections,
    }
