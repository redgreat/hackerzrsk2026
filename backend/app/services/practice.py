"""陪练会话编排：驱动 LangGraph、推送流式事件、同步业务表与成本。

每次图运行放在独立后台任务中执行，客户端断开（如跳转报告页）不会中断报告生成；
同一会话同一时刻只允许一个运行（单进程锁，多实例部署需改为分布式锁）。
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.db.models import ModelUsage, PracticeMessage, PracticeSession, User
from app.graph.state import PracticeContext
from app.services.llm.usage import UsageScope, usage_scope

logger = logging.getLogger(__name__)
Sink = Callable[[dict], Awaitable[None]]
MAX_INPUT_CHARS = 500


class PracticeService:
    def __init__(
        self,
        graph: CompiledStateGraph,
        ctx: PracticeContext,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self.graph = graph
        self.ctx = ctx
        self.sf = session_factory
        self._locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()

    @staticmethod
    def _config(sid: uuid.UUID) -> dict:
        return {"configurable": {"thread_id": str(sid)}}

    async def _owned(self, db: AsyncSession, sid: uuid.UUID, user: User) -> PracticeSession:
        sess = await db.get(PracticeSession, sid)
        if sess is None:
            raise NotFound("练习记录不存在")
        if sess.user_id != user.id:
            raise Forbidden("无权访问该练习")
        return sess

    async def _acquire(self, sid: uuid.UUID) -> asyncio.Lock:
        lock = self._locks.setdefault(sid, asyncio.Lock())
        if lock.locked():
            raise Conflict("上一条消息还在处理中，请稍候")
        await lock.acquire()  # 未被占用时立即获得，不会让出事件循环
        return lock

    async def _next_nodes(self, sid: uuid.UUID) -> tuple[str, ...]:
        return (await self.graph.aget_state(self._config(sid))).next

    # ---------- 图运行与落库 ----------

    async def _run(self, sid: uuid.UUID, user: User, cmd, sink: Sink) -> dict:
        config = self._config(sid)
        error: str | None = None
        with usage_scope() as usage:
            try:
                async for mode, chunk in self.graph.astream(
                    cmd, config, context=self.ctx, stream_mode=["custom", "updates"]
                ):
                    if mode == "custom":
                        await sink(chunk)
            except AppError as exc:
                error = exc.message
            except Exception:
                logger.exception("陪练图运行失败 session=%s", sid)
                error = "AI 服务开小差了，请重试"
        values = (await self.graph.aget_state(config)).values
        await self._persist(sid, user.id, values, usage)
        if error:
            await sink({"type": "error", "message": error})
        await sink({"type": "done", "status": values.get("status"), "turn": values.get("turn", 0)})
        return values

    async def _persist(self, sid: uuid.UUID, user_id: int, values: dict, usage: UsageScope) -> None:
        async with self.sf() as db, db.begin():
            sess = await db.get(PracticeSession, sid, with_for_update=True)
            max_seq = (
                await db.execute(
                    select(func.coalesce(func.max(PracticeMessage.seq), -1)).where(
                        PracticeMessage.session_id == sid
                    )
                )
            ).scalar_one()
            for t in values.get("transcript", []):
                if t["seq"] > max_seq:
                    db.add(
                        PracticeMessage(
                            session_id=sid,
                            seq=t["seq"],
                            turn=t["turn"],
                            role=t["role"],
                            content=t["content"],
                            trust_delta=t.get("trust_delta"),
                            trust_after=t.get("trust_after"),
                            inner_thought=t.get("inner_thought"),
                            meta=t.get("meta"),
                        )
                    )
            sess.status = values.get("status", sess.status)
            sess.turns = values.get("turn", 0)
            sess.hints_used = values.get("hints_used", 0)
            sess.final_trust = values.get("trust")
            report = values.get("report")
            if report and sess.report is None:
                sess.report = report
                sess.total_score = report["total_score"]
                sess.ended_at = datetime.now(UTC)
            self._add_usage(db, sess, user_id, usage)

    @staticmethod
    def _add_usage(db: AsyncSession, sess: PracticeSession | None, user_id: int, usage: UsageScope) -> None:
        for r in usage.records:
            db.add(
                ModelUsage(
                    session_id=sess.id if sess else None,
                    user_id=user_id,
                    purpose=r.purpose,
                    model=r.model,
                    prompt_tokens=r.prompt_tokens,
                    completion_tokens=r.completion_tokens,
                    audio_seconds=r.audio_seconds,
                    tts_chars=r.tts_chars,
                    cost_yuan=r.cost_yuan,
                    latency_ms=r.latency_ms,
                )
            )
        if sess is not None:
            sess.prompt_tokens += usage.prompt_tokens
            sess.completion_tokens += usage.completion_tokens
            sess.cost_yuan += usage.cost_yuan

    async def record_usage(self, sid: uuid.UUID | None, user: User, usage: UsageScope) -> None:
        """语音等图外调用的计量落库（计入会话成本）。"""
        if not usage.records:
            return
        async with self.sf() as db, db.begin():
            sess = None
            if sid is not None:
                sess = await db.get(PracticeSession, sid, with_for_update=True)
                if sess is not None and sess.user_id != user.id:
                    sess = None
            self._add_usage(db, sess, user.id, usage)

    async def _run_locked(self, sid: uuid.UUID, user: User, cmd, lock: asyncio.Lock, sink: Sink) -> dict:
        """lock 由调用方已获取，这里负责释放。"""
        try:
            return await self._run(sid, user, cmd, sink)
        finally:
            lock.release()

    async def _run_collect(
        self, sid: uuid.UUID, user: User, cmd, lock: asyncio.Lock | None = None
    ) -> tuple[dict, list[dict]]:
        events: list[dict] = []

        async def sink(ev: dict) -> None:
            events.append(ev)

        values = await self._run_locked(sid, user, cmd, lock or await self._acquire(sid), sink)
        if err := next((e for e in events if e["type"] == "error"), None):
            raise AppError(err["message"])
        return values, events

    # ---------- 业务接口 ----------

    async def start(self, user: User, scenario_id: str) -> dict:
        scenario = self.ctx.scenarios.get(scenario_id)
        sid = uuid.uuid4()
        async with self.sf() as db, db.begin():
            db.add(
                PracticeSession(id=sid, user_id=user.id, scenario_id=scenario.id, scenario_name=scenario.name)
            )
        await self._run_collect(
            sid, user, {"session_id": str(sid), "user_id": user.userid, "scenario_id": scenario.id}
        )
        return await self.detail(sid, user)

    async def open_message_stream(self, sid: uuid.UUID, user: User, text: str) -> AsyncIterator[dict]:
        """先同步校验（失败直接抛 HTTP 错误），再返回事件流。"""
        text = text.strip()
        if not text:
            raise AppError("说点什么吧")
        if len(text) > MAX_INPUT_CHARS:
            raise AppError(f"单条消息不超过 {MAX_INPUT_CHARS} 字")
        async with self.sf() as db:
            await self._owned(db, sid, user)
        lock = await self._acquire(sid)
        if await self._next_nodes(sid) != ("wait_input",):
            lock.release()
            raise Conflict("本次练习已结束")

        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        task = asyncio.create_task(
            self._run_locked(sid, user, Command(resume={"type": "message", "text": text}), lock, queue.put)
        )
        self._tasks.add(task)
        task.add_done_callback(lambda t: (self._tasks.discard(t), queue.put_nowait(None)))

        async def events() -> AsyncIterator[dict]:
            while (ev := await queue.get()) is not None:
                yield ev

        return events()

    async def hint(self, sid: uuid.UUID, user: User) -> str:
        async with self.sf() as db:
            await self._owned(db, sid, user)
        lock = await self._acquire(sid)
        if await self._next_nodes(sid) != ("wait_input",):
            lock.release()
            raise Conflict("本次练习已结束")
        values, _ = await self._run_collect(sid, user, Command(resume={"type": "hint"}), lock)
        return values.get("last_hint") or ""

    async def end(self, sid: uuid.UUID, user: User) -> dict:
        async with self.sf() as db:
            sess = await self._owned(db, sid, user)
            if sess.report:
                return sess.report
        lock = await self._acquire(sid)
        nxt = await self._next_nodes(sid)
        if "wait_input" in nxt:
            cmd = Command(resume={"type": "end"})
        elif "coach_report" in nxt:
            cmd = None  # 上次生成报告失败，从检查点续跑
        else:
            lock.release()
            raise Conflict("报告正在生成中，请稍候")
        values, _ = await self._run_collect(sid, user, cmd, lock)
        return values["report"]

    async def detail(self, sid: uuid.UUID, user: User) -> dict:
        async with self.sf() as db:
            sess = await self._owned(db, sid, user)
            rows = (
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
        scenario = self.ctx.scenarios.scenarios.get(sess.scenario_id)
        finished = sess.status != "ongoing"
        return {
            **session_summary(sess),
            "persona": {"name": scenario.persona.name, "role": scenario.persona.role} if scenario else None,
            "goal": scenario.goal if scenario else "",
            "opening_tip": scenario.opening.tip if scenario else None,
            "report_ready": sess.report is not None,
            "messages": [
                {
                    "seq": m.seq,
                    "turn": m.turn,
                    "role": m.role,
                    "content": m.content,
                    # 练习结束前隐藏客户内心与信任值
                    **(
                        {
                            "trust_after": m.trust_after,
                            "trust_delta": m.trust_delta,
                            "inner_thought": m.inner_thought,
                        }
                        if finished
                        else {}
                    ),
                }
                for m in rows
            ],
        }

    async def report(self, sid: uuid.UUID, user: User) -> dict | None:
        async with self.sf() as db:
            return (await self._owned(db, sid, user)).report

    async def list_sessions(self, user: User, limit: int = 30) -> list[dict]:
        async with self.sf() as db:
            rows = (
                (
                    await db.execute(
                        select(PracticeSession)
                        .where(PracticeSession.user_id == user.id)
                        .order_by(PracticeSession.started_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [session_summary(s) for s in rows]

    async def shutdown(self) -> None:
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=30)


def session_summary(s: PracticeSession) -> dict:
    return {
        "id": str(s.id),
        "scenario_id": s.scenario_id,
        "scenario_name": s.scenario_name,
        "status": s.status,
        "turns": s.turns,
        "hints_used": s.hints_used,
        "total_score": s.total_score,
        "cost_yuan": float(s.cost_yuan or 0),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
    }
