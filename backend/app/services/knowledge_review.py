"""知识事件核对：保留原始提取，人工修订单独存储，审核不启用检索。"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.core.errors import AppError, Conflict, NotFound
from app.db.models import KnowledgeEvent, TranscriptSnapshot
from app.services.transcripts import Labels, masked


class ReviewData(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    labels: Labels
    summary: str = Field(min_length=1, max_length=10000)
    applicability_limits: list[str] = Field(max_length=30)

    @model_validator(mode="after")
    def not_blank(self):
        if not self.title.strip() or not self.summary.strip():
            raise ValueError("标题和总结不能为空白")
        return self


class ReviewIn(BaseModel):
    expected_revision: int = Field(ge=0)
    action: Literal["save", "approve", "reject"]
    data: ReviewData
    note: str = Field("", max_length=2000)


def original(e: KnowledgeEvent) -> dict:
    return dict(
        title=e.title, labels=e.labels, summary=e.summary, applicability_limits=e.applicability_limits
    )


def card(e: KnowledgeEvent, s: TranscriptSnapshot) -> dict:
    return dict(
        id=e.id,
        title=(e.review_data or original(e))["title"],
        event_key=e.event_key,
        source_key=s.source_key,
        status=e.review_status,
        revision=e.review_revision,
        segment_start=e.segment_start,
        segment_end=e.segment_end,
    )


async def list_events(sf, status: str | None, page: int, size: int) -> dict:
    if status and status not in {"pending", "approved", "rejected"}:
        raise AppError("未知审核状态")
    conditions = [KnowledgeEvent.review_status == status] if status else []
    async with sf() as db:
        total = await db.scalar(select(func.count()).select_from(KnowledgeEvent).where(*conditions))
        rows = (
            await db.execute(
                select(KnowledgeEvent, TranscriptSnapshot)
                .join(TranscriptSnapshot, KnowledgeEvent.snapshot_id == TranscriptSnapshot.id)
                .where(*conditions)
                .order_by(KnowledgeEvent.id)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
    return {"total": total, "items": [card(e, s) for e, s in rows]}


async def get_event(sf, eid: int) -> dict:
    async with sf() as db:
        e = await db.get(KnowledgeEvent, eid)
        if e is None:
            raise NotFound("知识事件不存在")
        s = await db.get(TranscriptSnapshot, e.snapshot_id)
        return {
            **card(e, s),
            "data": e.review_data or original(e),
            "original": original(e),
            "evidence_seqs": e.evidence_seqs,
            "segments": s.segments,
            "speaker_mapping": s.speaker_mapping,
            "speaker_mapping_status": s.speaker_mapping_status,
            "privacy_status": s.privacy_status,
            "time_unit": s.time_unit,
            "policy_verification": e.policy_verification,
            "candidate_use": e.candidate_use,
            "history": e.review_history,
            "retrieval_enabled": False,
        }


async def review_event(sf, eid: int, user_id: int, body: ReviewIn) -> dict:
    if body.action == "reject" and not body.note.strip():
        raise AppError("驳回时请填写原因")
    async with sf() as db, db.begin():
        e = await db.get(KnowledgeEvent, eid, with_for_update=True)
        if e is None:
            raise NotFound("知识事件不存在")
        if e.review_revision != body.expected_revision:
            raise Conflict("内容已被其他操作更新，请重新打开后再修改")
        e.review_data = masked(body.data.model_dump())
        e.review_status = {"save": "pending", "approve": "approved", "reject": "rejected"}[body.action]
        e.review_revision += 1
        e.review_history = [
            *e.review_history,
            {
                "revision": e.review_revision,
                "action": body.action,
                "user_id": user_id,
                "at": datetime.now(UTC).isoformat(),
                "note": masked(body.note),
                "data": e.review_data,
            },
        ]
        # 修改后旧向量不能继续代表新内容；此阶段始终不启用检索。
        e.embedding = None
        e.embedding_model = None
    return await get_event(sf, eid)
