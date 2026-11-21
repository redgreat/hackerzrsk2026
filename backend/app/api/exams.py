"""员工端：考试与自测。"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, UserDep

router = APIRouter(prefix="/exams", tags=["exams"])


class AnswersIn(BaseModel):
    answers: dict[str, list[int]] = Field(max_length=200)


class RoleplayIn(BaseModel):
    key: str


@router.get("")
async def list_papers(c: ContainerDep, user: UserDep) -> list[dict]:
    return await c.exams.list_papers(user)


@router.get("/attempts")
async def my_attempts(c: ContainerDep, user: UserDep) -> list[dict]:
    return await c.exams.my_attempts(user)


@router.post("/{paper_id}/start")
async def start(paper_id: str, c: ContainerDep, user: UserDep) -> dict:
    return await c.exams.start(user, paper_id)


@router.get("/attempts/{aid}")
async def attempt(aid: uuid.UUID, c: ContainerDep, user: UserDep) -> dict:
    return await c.exams.view(aid, user)


@router.put("/attempts/{aid}/answers")
async def save_answers(aid: uuid.UUID, body: AnswersIn, c: ContainerDep, user: UserDep) -> dict:
    return await c.exams.save_answers(aid, user, body.answers)


@router.post("/attempts/{aid}/roleplay")
async def start_roleplay(aid: uuid.UUID, body: RoleplayIn, c: ContainerDep, user: UserDep) -> dict:
    return await c.exams.start_roleplay(aid, user, body.key)


@router.post("/attempts/{aid}/submit")
async def submit(aid: uuid.UUID, c: ContainerDep, user: UserDep) -> dict:
    return await c.exams.submit(aid, user)
