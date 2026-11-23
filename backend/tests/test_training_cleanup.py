"""培训清洗的证据检查、问题分流和独立存储测试，不调用真实模型。"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.db.models import KnowledgeEvent, TrainingCleanup, TranscriptSnapshot
from app.db.session import create_engine, create_session_factory
from app.services.training_cleanup import CleanupInput, CleanupOutput, classify, cleanup
from app.services.transcripts import ImportBatch, import_batch
from tests.test_transcripts import sample


def inputs(eid=1):
    return CleanupInput(
        event_id=eid,
        expected_revision=0,
        deidentified=True,
        lines=[
            {"seq": 1, "speaker": "customer", "text": "时间不确定"},
            {"seq": 2, "speaker": "agent", "text": "我记录为预计时间"},
        ],
    )


def output():
    return CleanupOutput(
        title="确认日期",
        summary="保留不确定性",
        labels={
            "customer_problem": "时间不确定",
            "stage": "确认",
            "agent_actions": ["澄清"],
            "observed_result": "无法判断",
        },
        dialogue=[
            {"speaker": "customer", "text": "目前日期还不确定。", "source_seqs": [1], "added": False},
            {"speaker": "agent", "text": "我先记录为预计日期。", "source_seqs": [2], "added": False},
        ],
        changes=["整理口语"],
        issues=[],
        learning_points=["不把预计当承诺"],
    )


def test_regular_cleanup_does_not_require_manual_approval():
    assert classify(output(), inputs()) == ("candidate", [])
    assert Settings(_env_file=None).llm.cleanup.timeout_seconds == 180


@pytest.mark.parametrize("problem", ["bad_reference", "bad_added_flag", "role", "major", "unknown"])
def test_major_problems_are_routed(problem):
    i, o = inputs(), output()
    if problem == "bad_reference":
        o.dialogue[0].source_seqs = [999]
    elif problem == "bad_added_flag":
        o.dialogue[0].added = True
    elif problem == "role":
        o.dialogue[0].speaker = "agent"
    elif problem == "major":
        from app.services.training_cleanup import Issue

        o.issues = [Issue(severity="major", category="logic", description="关键事实缺失")]
    else:
        i.lines[0].speaker = "unknown"
    assert classify(o, i)[0] == "review_required"


def test_input_requires_explicit_deidentification_and_order():
    data = inputs().model_dump()
    data["deidentified"] = False
    with pytest.raises(ValidationError):
        CleanupInput.model_validate(data)
    data["deidentified"] = True
    data["lines"].reverse()
    with pytest.raises(ValidationError):
        CleanupInput.model_validate(data)


@pytest.mark.skipif(not os.getenv("TEST_TRANSCRIPT_DATABASE_URL"), reason="未设置独立存储测试库")
async def test_cleanup_is_separate_and_checks_stale_inputs():
    engine = create_engine(Settings(_env_file=None, database_url=os.environ["TEST_TRANSCRIPT_DATABASE_URL"]))
    sf = create_session_factory(engine)
    try:
        data = sample()
        data["cases"][0]["segments"].append(
            {"seq": 2, "channel": 1, "start_raw": 1, "end_raw": 2, "text": "我记录为预计时间"}
        )
        data["events"][0]["source_segment_range"] = [1, 2]
        batch = ImportBatch.model_validate(data)
        await import_batch(sf, batch)
        async with sf() as db:
            eid = await db.scalar(
                select(KnowledgeEvent.id)
                .join(TranscriptSnapshot)
                .where(TranscriptSnapshot.source_key == batch.cases[0].case_key)
            )
        llm = SimpleNamespace(
            cfg=SimpleNamespace(provider="openai"),
            model_name=lambda _: "test-model",
            structured=AsyncMock(return_value=output()),
        )
        result = await cleanup(sf, llm, inputs(eid))
        assert result["status"] == "candidate"
        async with sf() as db:
            event = await db.get(KnowledgeEvent, eid)
            run = await db.get(TrainingCleanup, result["id"])
            assert event.review_revision == 0 and event.review_status == "pending"
            assert run.result["dialogue"] and run.prompt_version == "cleanup-v1"
        stale = inputs(eid)
        stale.expected_revision = 9
        with pytest.raises(Conflict):
            await cleanup(sf, llm, stale)
        shortened = inputs(eid)
        shortened.lines[1].seq = 3
        with pytest.raises(AppError):
            await cleanup(sf, llm, shortened)
        assert llm.structured.await_count == 1
    finally:
        await engine.dispose()
