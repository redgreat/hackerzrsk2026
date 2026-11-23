"""已有转写与人工提取结果导入。只存基础脱敏文本，默认待审核，不调用外部模型。"""

import asyncio
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import KnowledgeEvent, TranscriptSnapshot
from app.services.guard import mask_pii


class Segment(BaseModel):
    seq: int = Field(ge=1)
    channel: int
    start_raw: int = Field(ge=0)
    end_raw: int = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def check_time(self):
        if self.end_raw < self.start_raw:
            raise ValueError("片段结束时间早于开始时间")
        return self


class Case(BaseModel):
    case_key: str = Field(min_length=1, max_length=128)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_file: str
    source_labels: str
    segments: list[Segment] = Field(min_length=1)
    speaker_mapping: dict[str, str]
    speaker_mapping_status: str = Field(max_length=64)
    time_unit: str = Field(max_length=32)


class Labels(BaseModel):
    customer_problem: str
    stage: str
    agent_actions: list[str]
    observed_result: str


class Event(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    case_key: str
    source_segment_range: tuple[int, int]
    key_evidence_seqs: list[int] = Field(min_length=1)
    title: str = Field(min_length=1, max_length=256)
    labels: Labels
    derived_summary: str
    applicability_limits: list[str]
    candidate_use: str = Field(max_length=64)
    policy_verification: str = Field(max_length=32)


class ImportBatch(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    # 未声明的 full_export_text/context_segments 等原始副本不会写入数据库。
    schema_version: str = Field(min_length=1, max_length=64)
    cases: list[Case] = Field(min_length=1)
    events: list[Event]

    @model_validator(mode="after")
    def check_references(self):
        cases = {c.case_key: c for c in self.cases}
        if len(cases) != len(self.cases):
            raise ValueError("批次内来源标识重复")
        for c in self.cases:
            seqs = [s.seq for s in c.segments]
            if seqs != list(range(1, len(seqs) + 1)):
                raise ValueError("完整转写的片段编号必须从 1 连续递增")
        keys = set()
        for e in self.events:
            if e.case_key not in cases:
                raise ValueError("事件来源不存在")
            lo, hi = e.source_segment_range
            if not 1 <= lo <= hi <= len(cases[e.case_key].segments):
                raise ValueError("事件原文范围越界")
            if any(not lo <= seq <= hi for seq in e.key_evidence_seqs):
                raise ValueError("证据编号不在事件范围内")
            key = (e.case_key, e.event_id)
            if key in keys:
                raise ValueError("批次内事件编号重复")
            keys.add(key)
        return self


def masked(value):
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, list):
        return [masked(v) for v in value]
    if isinstance(value, dict):
        return {k: masked(v) for k, v in value.items()}
    return value


async def import_batch(sf, batch: ImportBatch) -> dict:
    counts = {"snapshots_created": 0, "events_created": 0}
    async with sf() as db, db.begin():
        snapshots = {}
        for c in batch.cases:
            values = dict(
                source_key=c.case_key,
                source_hash=c.source_sha256,
                source_file=c.source_file,
                source_labels=mask_pii(c.source_labels),
                segments=masked([s.model_dump() for s in c.segments]),
                speaker_mapping=c.speaker_mapping,
                speaker_mapping_status=c.speaker_mapping_status,
                time_unit=c.time_unit,
                privacy_status="pending",
            )
            sid = (
                await db.execute(
                    insert(TranscriptSnapshot)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=["source_key", "source_hash"])
                    .returning(TranscriptSnapshot.id)
                )
            ).scalar_one_or_none()
            if sid is not None:
                counts["snapshots_created"] += 1
            else:
                sid = (
                    await db.execute(
                        select(TranscriptSnapshot.id).where(
                            TranscriptSnapshot.source_key == c.case_key,
                            TranscriptSnapshot.source_hash == c.source_sha256,
                        )
                    )
                ).scalar_one()
            snapshots[c.case_key] = sid
        for e in batch.events:
            content = masked(e.model_dump())
            digest = hashlib.sha256(
                json.dumps(
                    {"version": batch.schema_version, "event": content}, ensure_ascii=False, sort_keys=True
                ).encode()
            ).hexdigest()
            stmt = (
                insert(KnowledgeEvent)
                .values(
                    snapshot_id=snapshots[e.case_key],
                    event_key=e.event_id,
                    extraction_hash=digest,
                    extraction_version=batch.schema_version,
                    title=content["title"],
                    segment_start=e.source_segment_range[0],
                    segment_end=e.source_segment_range[1],
                    evidence_seqs=e.key_evidence_seqs,
                    labels=content["labels"],
                    summary=content["derived_summary"],
                    applicability_limits=content["applicability_limits"],
                    candidate_use=e.candidate_use,
                    policy_verification=e.policy_verification,
                    review_status="pending",
                )
                .on_conflict_do_nothing(index_elements=["snapshot_id", "event_key", "extraction_hash"])
            )
            result = await db.execute(stmt.returning(KnowledgeEvent.id))
            counts["events_created"] += result.scalar_one_or_none() is not None
    return counts


async def import_file(sf, path: Path) -> dict:
    # 先验证完整批次，再打开事务，避免部分导入。
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    batch = ImportBatch.model_validate_json(text)
    return await import_batch(sf, batch)
