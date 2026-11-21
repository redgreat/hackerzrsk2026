"""员工端：优质录音库（仅已发布）。"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ContainerDep, UserDep

router = APIRouter(prefix="/recordings", tags=["recordings"])


class CheckIn(BaseModel):
    answer: list[int]


@router.get("")
async def list_recordings(
    c: ContainerDep,
    _: UserDep,
    q: str | None = None,
    customer_type: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    return await c.recordings.list_published(q, customer_type, page, size)


@router.get("/{rid}")
async def recording_detail(rid: int, c: ContainerDep, _: UserDep) -> dict:
    return await c.recordings.detail_published(rid)


@router.post("/{rid}/played")
async def played(rid: int, c: ContainerDep, _: UserDep) -> dict:
    await c.recordings.mark_played(rid)
    return {"ok": True}


@router.post("/{rid}/questions/{qid}/check")
async def check(rid: int, qid: int, body: CheckIn, c: ContainerDep, _: UserDep) -> dict:
    return await c.recordings.check_question(rid, qid, body.answer)
