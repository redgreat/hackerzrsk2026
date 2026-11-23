"""转写导入的证据校验、脱敏及可选 PostgreSQL 幂等测试。"""

import os
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import KnowledgeEvent, TranscriptSnapshot
from app.db.session import create_engine, create_session_factory
from app.services.transcripts import ImportBatch, import_batch, masked


def sample():
    key = "test:" + uuid.uuid4().hex
    return {
        "schema_version": "test-v1",
        "cases": [
            {
                "case_key": key,
                "source_sha256": "a" * 64,
                "source_file": "private.json",
                "source_labels": "示例",
                "full_export_text": "此字段不能落库",
                "segments": [
                    {"seq": 1, "channel": 0, "start_raw": 0, "end_raw": 1, "text": "联系13812345678"}
                ],
                "speaker_mapping": {"0": "customer"},
                "speaker_mapping_status": "unverified",
                "time_unit": "unverified",
            }
        ],
        "events": [
            {
                "event_id": "E01",
                "case_key": key,
                "source_segment_range": [1, 1],
                "key_evidence_seqs": [1],
                "title": "测试",
                "labels": {
                    "customer_problem": "其他",
                    "stage": "其他",
                    "agent_actions": [],
                    "observed_result": "无法判断",
                },
                "derived_summary": "联系13812345678",
                "applicability_limits": ["待核验"],
                "candidate_use": "communication_example",
                "policy_verification": "unverified",
                "review_status": "approved",
                "retrieval_enabled": True,
            }
        ],
    }


def test_raw_export_and_input_approval_are_not_importable():
    batch = ImportBatch.model_validate(sample())
    assert "full_export_text" not in batch.cases[0].model_dump()
    assert "review_status" not in batch.events[0].model_dump()
    assert masked({"text": "联系13812345678"}) == {"text": "联系[手机号]"}


@pytest.mark.parametrize("change", ["missing_case", "bad_evidence", "incomplete_transcript"])
def test_invalid_evidence_is_rejected(change):
    data = sample()
    if change == "missing_case":
        data["events"][0]["case_key"] = "missing"
    elif change == "bad_evidence":
        data["events"][0]["key_evidence_seqs"] = [2]
    else:
        data["cases"][0]["segments"][0]["seq"] = 2
    with pytest.raises(ValidationError):
        ImportBatch.model_validate(data)


@pytest.mark.skipif(not os.getenv("TEST_TRANSCRIPT_DATABASE_URL"), reason="未设置独立存储测试库")
async def test_database_import_is_pending_idempotent_and_versioned():
    engine = create_engine(Settings(_env_file=None, database_url=os.environ["TEST_TRANSCRIPT_DATABASE_URL"]))
    sf = create_session_factory(engine)
    try:
        data = sample()
        batch = ImportBatch.model_validate(data)
        assert await import_batch(sf, batch) == {"snapshots_created": 1, "events_created": 1}
        assert await import_batch(sf, batch) == {"snapshots_created": 0, "events_created": 0}
        async with sf() as db:
            snapshot = (
                await db.execute(
                    select(TranscriptSnapshot).where(TranscriptSnapshot.source_key == batch.cases[0].case_key)
                )
            ).scalar_one()
            event = (
                await db.execute(select(KnowledgeEvent).where(KnowledgeEvent.snapshot_id == snapshot.id))
            ).scalar_one()
            assert snapshot.privacy_status == event.review_status == "pending"
            assert "13812345678" not in snapshot.segments[0]["text"] + event.summary
            assert event.embedding is None
        data["schema_version"] = "test-v2"
        assert await import_batch(sf, ImportBatch.model_validate(data)) == {
            "snapshots_created": 0,
            "events_created": 1,
        }
        data["cases"][0]["source_sha256"] = "b" * 64
        assert await import_batch(sf, ImportBatch.model_validate(data)) == {
            "snapshots_created": 1,
            "events_created": 1,
        }
        async with sf() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(TranscriptSnapshot)
                .where(TranscriptSnapshot.source_key == batch.cases[0].case_key)
            )
            assert count == 2
    finally:
        await engine.dispose()
