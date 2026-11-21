"""管理后台：录音管理（转写/分析/发布）、录音题目审核、考试成绩。"""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, ContainerDep
from app.services.exams import paper_card
from app.services.recording_source import RecordingItem

router = APIRouter(prefix="/admin", tags=["admin-training"])


class RecordingIn(BaseModel):
    audio_url: str = Field(min_length=8, max_length=2000, pattern=r"^https?://")
    title: str = Field("", max_length=128)


class RecordingPatch(BaseModel):
    title: str | None = Field(None, max_length=128)
    customer_type: str | None = Field(None, max_length=32)
    tags: list[str] | None = Field(None, max_length=8)
    published: bool | None = None


class ProcessIn(BaseModel):
    force: bool = False


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
    return await c.recordings.admin_list(status, published, q, page, size)


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


@router.patch("/recordings/{rid}")
async def patch_recording(rid: int, body: RecordingPatch, c: ContainerDep, _: AdminDep) -> dict:
    return await c.recordings.update(rid, **body.model_dump())


@router.post("/recordings/{rid}/process")
async def process_recording(rid: int, body: ProcessIn, c: ContainerDep, admin: AdminDep) -> dict:
    """后台执行转写 + AI 分析，前端轮询详情查看进度。"""
    c.recordings.process_in_background(rid, body.force, admin.id)
    return {"accepted": True}


@router.patch("/recording-questions/{qid}")
async def patch_question(qid: int, body: QuestionPatch, c: ContainerDep, _: AdminDep) -> dict:
    data = body.model_dump()
    return await c.recordings.review_question(qid, data.pop("status"), **data)


@router.get("/exams/papers")
async def papers(c: ContainerDep, _: AdminDep) -> list[dict]:
    return [
        {**paper_card(p), "department": p.department, "enabled": p.enabled}
        for p in c.exams.registry.papers.values()
    ]


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
