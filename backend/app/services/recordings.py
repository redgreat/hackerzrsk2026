"""优质录音：导入 → 转写（Paraformer）→ AI 分析（亮点/合规/题目）→ 管理员审核发布 → 员工收听学习。

- 音频本身留在 OSS，只存地址；转写文本落库前脱敏。
- 未发布的录音员工不可见；发布时把亮点话术写入知识库（来源 recording:<id>），取消发布即移除。
- 计量（asr / analyst）写入 model_usage，不记录内容。
"""

import asyncio
import logging
import random
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound
from app.db.models import Recording, RecordingQuestion
from app.graph.schemas import RecordingAnalysis
from app.prompts.analyst import analyst_messages_text
from app.services import recording_rules as rr
from app.services.file_asr import FileASR
from app.services.knowledge import KnowledgeBase, ParsedChunk
from app.services.llm import LLMGateway
from app.services.llm.usage import UsageScope, usage_scope
from app.services.practice import PracticeService
from app.services.recording_source import RecordingItem, normalize_url
from app.services.scenarios import ScenarioRegistry

logger = logging.getLogger(__name__)
BUSY = ("transcribing", "analyzing")


def check_answer(qtype: str, answer: list[int], chosen: list[int]) -> bool:
    return sorted(set(chosen)) == sorted(set(answer)) if qtype == "multi" else chosen[:1] == answer[:1]


class RecordingService:
    def __init__(
        self,
        settings: Settings,
        sf: async_sessionmaker[AsyncSession],
        llm: LLMGateway,
        scenarios: ScenarioRegistry,
        knowledge: KnowledgeBase | None,
        asr: FileASR | None = None,
    ):
        self.settings = settings
        self.sf = sf
        self.llm = llm
        self.scenarios = scenarios
        self.knowledge = knowledge
        self.asr = asr or FileASR(settings.recordings)
        self._tasks: set[asyncio.Task] = set()

    # ---------- 导入与处理 ----------

    async def import_items(self, items: list[RecordingItem], source: str) -> tuple[int, int]:
        created = 0
        async with self.sf() as db, db.begin():
            for it in items:
                res = await db.execute(
                    insert(Recording)
                    .values(
                        source=source,
                        source_key=it.source_key,
                        audio_url=it.audio_url,
                        title=it.title,
                        duration_seconds=it.duration_seconds,
                        meta=it.meta or None,
                        tags=[],
                    )
                    .on_conflict_do_nothing(index_elements=["source_key"])
                    .returning(Recording.id)
                )
                created += res.first() is not None
        return created, len(items) - created

    async def _set(self, rid: int, **values) -> None:
        async with self.sf() as db, db.begin():
            await db.execute(update(Recording).where(Recording.id == rid).values(**values))

    async def _record_usage(self, usage: UsageScope, user_id: int | None) -> None:
        if usage.records:
            async with self.sf() as db, db.begin():
                PracticeService._add_usage(db, None, user_id, usage)

    async def process(self, rid: int, force: bool = False, user_id: int | None = None) -> dict:
        """转写（如需要）+ 分析。失败时状态置为 failed 并记录原因，不抛出。"""
        async with self.sf() as db, db.begin():
            rec = await db.get(Recording, rid, with_for_update=True)
            if rec is None:
                raise NotFound("录音不存在")
            if rec.status in BUSY and not force:
                raise Conflict("该录音正在处理中")
            need_asr = force or not rec.transcript
            rec.status, rec.error = ("transcribing" if need_asr else "analyzing"), None
            url = normalize_url(rec.audio_url, self.settings.recordings.audio_base_url)
            task_id = rec.asr_task_id if not force else None
        with usage_scope() as usage:
            try:
                if need_asr:

                    async def saved(tid: str) -> None:
                        await self._set(rid, asr_task_id=tid)

                    result = await self.asr.transcribe(url, task_id, saved)
                    transcript = rr.build_transcript(rr.parse_paraformer(result))
                    if not transcript:
                        raise AppError("转写结果为空（可能是静音或无法识别的录音）")
                    await self._set(
                        rid,
                        transcript=transcript,
                        duration_seconds=rr.duration_seconds(result, transcript),
                        status="analyzing",
                    )
                await self._analyze(rid)
            except Exception as exc:
                msg = exc.message if isinstance(exc, AppError) else "处理失败，详见服务日志"
                if not isinstance(exc, AppError):
                    logger.exception("录音处理失败 id=%s", rid)
                await self._set(rid, status="failed", error=msg[:500])
            finally:
                await self._record_usage(usage, user_id)
        return await self.admin_detail(rid)

    async def _analyze(self, rid: int) -> None:
        async with self.sf() as db:
            rec = await db.get(Recording, rid)
            transcript = rec.transcript or []
        rubric = self.scenarios.rubrics[self.settings.recordings.rubric_id]
        candidates = [s for s in self.scenarios.list() if s.scoring == rubric.id]
        system, user = analyst_messages_text(transcript, rubric, candidates)
        out = await self.llm.structured(
            "analyst", [SystemMessage(content=system), HumanMessage(content=user)], RecordingAnalysis
        )
        n = len(transcript)
        valid_ids = {s.id for s in candidates}
        analysis = out.model_dump(exclude={"questions"})
        analysis["highlights"] = [
            h
            for h in analysis["highlights"]
            if 0 <= h["index"] < n and transcript[h["index"]]["speaker"] == "agent"
        ]
        analysis["stages"] = [s for s in analysis["stages"] if 0 <= s["start_index"] < n]
        analysis["related_scenario_ids"] = [s for s in analysis["related_scenario_ids"] if s in valid_ids]
        async with self.sf() as db, db.begin():
            rec = await db.get(Recording, rid, with_for_update=True)
            rec.analysis = analysis
            rec.title = rec.title or out.title[:128]
            rec.customer_type = out.customer_type[:32]
            rec.tags = rec.tags or [t[:32] for t in out.tags[:5]]
            rec.status = "ready"
            # 重新分析时替换未审核的旧题目，已审核/已驳回的保留
            old = (
                await db.execute(
                    select(RecordingQuestion).where(
                        RecordingQuestion.recording_id == rid, RecordingQuestion.status == "pending"
                    )
                )
            ).scalars()
            for q in old:
                await db.delete(q)
            for q in out.questions:
                if len(q.options) < 2 or not q.answer or any(not 0 <= a < len(q.options) for a in q.answer):
                    continue
                db.add(
                    RecordingQuestion(
                        recording_id=rid,
                        type=q.type,
                        stem=q.stem,
                        options=q.options,
                        answer=q.answer if q.type == "multi" else q.answer[:1],
                        explanation=q.explanation,
                    )
                )

    def process_in_background(self, rid: int, force: bool, user_id: int | None) -> None:
        task = asyncio.create_task(self.process(rid, force, user_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def process_pending(self, limit: int, concurrency: int = 3) -> list[dict]:
        async with self.sf() as db:
            ids = (
                (
                    await db.execute(
                        select(Recording.id)
                        .where(Recording.status.in_(("imported", "failed", "transcribed")))
                        .order_by(Recording.id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        sem = asyncio.Semaphore(concurrency)

        async def one(rid: int) -> dict:
            async with sem:
                return await self.process(rid)

        return await asyncio.gather(*(one(r) for r in ids))

    async def shutdown(self) -> None:
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=30)

    # ---------- 管理员 ----------

    async def admin_list(
        self, status: str | None, published: bool | None, q: str | None, page: int, size: int
    ) -> dict:
        cond = []
        if status:
            cond.append(Recording.status == status)
        if published is not None:
            cond.append(Recording.published.is_(published))
        if q:
            cond.append(Recording.title.ilike(f"%{q}%") | Recording.customer_type.ilike(f"%{q}%"))
        size = max(1, min(size, 100))
        pending_q = (
            select(RecordingQuestion.recording_id, func.count().label("n"))
            .where(RecordingQuestion.status == "pending")
            .group_by(RecordingQuestion.recording_id)
            .subquery()
        )
        async with self.sf() as db:
            total = (await db.execute(select(func.count()).select_from(Recording).where(*cond))).scalar_one()
            rows = (
                await db.execute(
                    select(Recording, pending_q.c.n)
                    .outerjoin(pending_q, pending_q.c.recording_id == Recording.id)
                    .where(*cond)
                    .order_by(Recording.id.desc())
                    .offset((max(page, 1) - 1) * size)
                    .limit(size)
                )
            ).all()
            counts = dict(
                (await db.execute(select(Recording.status, func.count()).group_by(Recording.status))).all()
            )
        return {
            "total": total,
            "status_counts": counts,
            "items": [{**_card(r), "pending_questions": n or 0} for r, n in rows],
        }

    async def admin_detail(self, rid: int) -> dict:
        async with self.sf() as db:
            rec = await db.get(Recording, rid)
            if rec is None:
                raise NotFound("录音不存在")
            qs = (
                (
                    await db.execute(
                        select(RecordingQuestion)
                        .where(RecordingQuestion.recording_id == rid)
                        .order_by(RecordingQuestion.id)
                    )
                )
                .scalars()
                .all()
            )
        return {**_detail(rec), "source_key": rec.source_key, "questions": [_question(q, True) for q in qs]}

    async def update(self, rid: int, **fields) -> dict:
        async with self.sf() as db, db.begin():
            rec = await db.get(Recording, rid, with_for_update=True)
            if rec is None:
                raise NotFound("录音不存在")
            publish = fields.pop("published", None)
            for k, v in fields.items():
                if v is not None:
                    setattr(rec, k, v)
            if publish is not None and publish != rec.published:
                if publish and rec.status != "ready":
                    raise AppError("录音尚未完成转写与分析，不能发布")
                rec.published = publish
                rec.published_at = datetime.now(UTC) if publish else None
            snapshot = (rec.id, rec.published, rec.title, rec.transcript, rec.analysis)
        await self._sync_knowledge(*snapshot)
        return await self.admin_detail(rid)

    async def _sync_knowledge(self, rid: int, published: bool, title: str, transcript, analysis) -> None:
        if self.knowledge is None:
            return
        source = f"recording:{rid}"
        chunks = []
        if published and analysis and transcript:
            for h in analysis.get("highlights", []):
                chunks.append(
                    ParsedChunk(
                        source=source,
                        title=f"优秀录音·{title}·{h['technique']}",
                        content=f"坐席：{transcript[h['index']]['text']}\n要点：{h['why']}",
                        tags=["优秀录音", h["technique"]],
                        scenario_ids=analysis.get("related_scenario_ids", []),
                    )
                )
        await self.knowledge.replace_source(source, chunks)

    async def review_question(self, qid: int, status: str | None, **fields) -> dict:
        async with self.sf() as db, db.begin():
            q = await db.get(RecordingQuestion, qid, with_for_update=True)
            if q is None:
                raise NotFound("题目不存在")
            for k, v in fields.items():
                if v is not None:
                    setattr(q, k, v)
            if any(not 0 <= a < len(q.options) for a in q.answer) or not q.answer:
                raise AppError("答案下标超出选项范围")
            if status:
                q.status = status
        return _question(q, True)

    # ---------- 员工 ----------

    async def list_published(self, q: str | None, customer_type: str | None, page: int, size: int) -> dict:
        cond = [Recording.published.is_(True)]
        if customer_type:
            cond.append(Recording.customer_type == customer_type)
        if q:
            cond.append(
                Recording.title.ilike(f"%{q}%") | func.array_to_string(Recording.tags, ",").ilike(f"%{q}%")
            )
        size = max(1, min(size, 50))
        async with self.sf() as db:
            total = (await db.execute(select(func.count()).select_from(Recording).where(*cond))).scalar_one()
            rows = (
                (
                    await db.execute(
                        select(Recording)
                        .where(*cond)
                        .order_by(Recording.published_at.desc().nulls_last(), Recording.id.desc())
                        .offset((max(page, 1) - 1) * size)
                        .limit(size)
                    )
                )
                .scalars()
                .all()
            )
            types = (
                await db.execute(
                    select(Recording.customer_type, func.count())
                    .where(Recording.published.is_(True))
                    .group_by(Recording.customer_type)
                )
            ).all()
        return {
            "total": total,
            "customer_types": [{"name": t or "其他", "count": n} for t, n in types],
            "items": [_card(r) for r in rows],
        }

    async def _published(self, db: AsyncSession, rid: int) -> Recording:
        rec = await db.get(Recording, rid)
        if rec is None or not rec.published:
            raise NotFound("录音不存在或未发布")
        return rec

    async def detail_published(self, rid: int) -> dict:
        async with self.sf() as db:
            rec = await self._published(db, rid)
            qs = (
                (
                    await db.execute(
                        select(RecordingQuestion)
                        .where(RecordingQuestion.recording_id == rid, RecordingQuestion.status == "approved")
                        .order_by(RecordingQuestion.id)
                    )
                )
                .scalars()
                .all()
            )
        related = [
            {"id": s.id, "name": s.name}
            for sid in (rec.analysis or {}).get("related_scenario_ids", [])
            if (s := self.scenarios.scenarios.get(sid)) and s.enabled
        ]
        return {**_detail(rec), "related_scenarios": related, "questions": [_question(q, False) for q in qs]}

    async def mark_played(self, rid: int) -> None:
        async with self.sf() as db, db.begin():
            await self._published(db, rid)
            await db.execute(
                update(Recording).where(Recording.id == rid).values(play_count=Recording.play_count + 1)
            )

    async def check_question(self, rid: int, qid: int, chosen: list[int]) -> dict:
        async with self.sf() as db:
            await self._published(db, rid)
            q = await db.get(RecordingQuestion, qid)
        if q is None or q.recording_id != rid or q.status != "approved":
            raise NotFound("题目不存在")
        return {
            "correct": check_answer(q.type, q.answer, chosen),
            "answer": q.answer,
            "explanation": q.explanation,
        }

    async def sample_questions(self, count: int) -> list[dict]:
        """考试抽题：已发布录音的已审核题目，附带录音信息（含答案，仅供服务端出题快照）。"""
        async with self.sf() as db:
            rows = (
                await db.execute(
                    select(RecordingQuestion, Recording)
                    .join(Recording, Recording.id == RecordingQuestion.recording_id)
                    .where(RecordingQuestion.status == "approved", Recording.published.is_(True))
                )
            ).all()
        picked = random.sample(rows, min(count, len(rows)))
        return [
            {
                **_question(q, True),
                "recording": {
                    "id": r.id,
                    "title": r.title,
                    "audio_url": r.audio_url,
                    "duration_seconds": r.duration_seconds,
                },
            }
            for q, r in picked
        ]


def _card(r: Recording) -> dict:
    a = r.analysis or {}
    return {
        "id": r.id,
        "title": r.title or f"录音 #{r.id}",
        "customer_type": r.customer_type,
        "outcome": a.get("outcome"),
        "summary": a.get("summary"),
        "tags": r.tags or [],
        "duration_seconds": r.duration_seconds,
        "status": r.status,
        "error": r.error,
        "published": r.published,
        "play_count": r.play_count,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "published_at": r.published_at.isoformat() if r.published_at else None,
    }


def _detail(r: Recording) -> dict:
    return {**_card(r), "audio_url": r.audio_url, "transcript": r.transcript or [], "analysis": r.analysis}


def _question(q: RecordingQuestion, with_answer: bool) -> dict:
    d = {"id": q.id, "recording_id": q.recording_id, "type": q.type, "stem": q.stem, "options": q.options}
    if with_answer:
        d.update(answer=q.answer, explanation=q.explanation, status=q.status)
    return d
