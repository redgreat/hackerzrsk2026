"""管理后台：录音管理（转写/分析/发布）、录音题目审核、考试成绩。"""

import uuid
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, ContainerDep
from app.services.recording_source import RecordingItem

router = APIRouter(prefix="/admin", tags=["admin-training"])


class RecordingIn(BaseModel):
    audio_url: str = Field(min_length=8, max_length=2000, pattern=r"^https?://")
    title: str = Field("", max_length=128)


class RecordingImportIn(BaseModel):
    limit: int = Field(5, ge=1, le=10)
    call_id: int | None = Field(None, ge=1)


class RecordingPatch(BaseModel):
    title: str | None = Field(None, max_length=128)
    customer_type: str | None = Field(None, max_length=32)
    tags: list[str] | None = Field(None, max_length=8)
    published: bool | None = None
    extracted_scenario_ids: list[str] | None = Field(None, max_length=20)
    learning_note: str | None = Field(None, max_length=600)
    transcript_snapshot_id: int | None = Field(None, ge=1)


class GeneratePracticesIn(BaseModel):
    first: int | None = Field(None, ge=1)
    last: int | None = Field(None, ge=1)


class ReviewPracticeIn(BaseModel):
    status: Literal["approved", "archived"]


class QuestionPatch(BaseModel):
    status: Literal["pending", "approved", "rejected"] | None = None
    stem: str | None = Field(None, min_length=2, max_length=500)
    options: list[str] | None = Field(None, min_length=2, max_length=6)
    answer: list[int] | None = Field(None, min_length=1)
    explanation: str | None = Field(None, max_length=500)


@router.get("/recordings")
async def recordings(
    c: ContainerDep,
    _: AdminDep,
    status: str | None = None,
    published: bool | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    result = await c.recordings.admin_list(status, published, q, page, size)
    return {**result, "can_clear_recordings": c.settings.app_env == "dev"}


@router.post("/recordings")
async def add_recording(body: RecordingIn, c: ContainerDep, _: AdminDep) -> dict:
    """手工添加一条录音地址（批量导入请用 CLI：import-recordings）。"""
    created, _skipped = await c.recordings.import_items(
        [RecordingItem(source_key=f"manual:{body.audio_url}", audio_url=body.audio_url, title=body.title)],
        "manual",
    )
    return {"created": created}


@router.get("/recordings/{rid}")
async def recording(rid: int, c: ContainerDep, _: AdminDep) -> dict:
    return await c.recordings.admin_detail(rid)


@router.post("/recordings/import-dbmcp")
async def import_dbmcp_recordings(body: RecordingImportIn, c: ContainerDep, _: AdminDep) -> dict:
    return await c.recordings.import_from_dbmcp(body.limit, body.call_id)


@router.delete("/recordings")
async def clear_recordings(c: ContainerDep, _: AdminDep) -> dict:
    return await c.recordings.clear_recording_data()


@router.patch("/recordings/{rid}")
async def patch_recording(rid: int, body: RecordingPatch, c: ContainerDep, _: AdminDep) -> dict:
    return await c.recordings.update(rid, **body.model_dump())


@router.get("/recording-transcripts")
async def recording_transcripts(c: ContainerDep, _: AdminDep) -> list[dict]:
    return await c.recordings.list_transcripts()


@router.post("/recordings/{rid}/practices")
async def generate_practices(rid: int, body: GeneratePracticesIn, c: ContainerDep, admin: AdminDep) -> dict:
    return await c.recordings.generate_practices(rid, body.first, body.last, admin.id)


@router.patch("/recordings/{rid}/practices/{sid}")
async def review_practice(rid: int, sid: str, body: ReviewPracticeIn, c: ContainerDep, _: AdminDep) -> dict:
    return await c.recordings.review_practice(rid, sid, body.status)


@router.patch("/recording-questions/{qid}")
async def patch_question(qid: int, body: QuestionPatch, c: ContainerDep, _: AdminDep) -> dict:
    data = body.model_dump()
    return await c.recordings.review_question(qid, data.pop("status"), **data)


@router.get("/exams/papers")
async def papers(c: ContainerDep, _: AdminDep) -> list[dict]:
    return await c.exams.admin_papers()


class GenerateExamQuestionsIn(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=32)
    count: int = Field(6, ge=1, le=8)


class ExamQuestionReviewIn(BaseModel):
    status: Literal["approved", "archived"]


@router.get("/exams/question-sources")
async def exam_question_sources(c: ContainerDep, _: AdminDep) -> list[dict]:
    return await c.exams.question_bank.sources()


@router.get("/exams/questions")
async def exam_questions(
    c: ContainerDep,
    _: AdminDep,
    status: Literal["pending", "approved", "archived"] | None = None,
    page: int = Query(1, ge=1),
) -> dict:
    return await c.exams.question_bank.list_questions(status, page)


@router.post("/exams/questions/generate")
async def generate_exam_questions(body: GenerateExamQuestionsIn, c: ContainerDep, user: AdminDep) -> dict:
    return await c.exams.question_bank.generate(body.scenario_id, body.count, user.id)


@router.patch("/exams/questions/{question_id}")
async def review_exam_question(
    question_id: int, body: ExamQuestionReviewIn, c: ContainerDep, _: AdminDep
) -> dict:
    await c.exams.question_bank.review(question_id, body.status)
    return {"ok": True}


@router.get("/exams/attempts")
async def attempts(
    c: ContainerDep,
    _: AdminDep,
    paper_id: str | None = None,
    user_id: int | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    return await c.exams.admin_list(paper_id, user_id, page, size)


@router.get("/exams/attempts/{aid}")
async def attempt(aid: uuid.UUID, c: ContainerDep, _: AdminDep) -> dict:
    return await c.exams.admin_detail(aid)
