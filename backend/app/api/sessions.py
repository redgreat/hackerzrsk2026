import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, UserDep
from app.core.errors import NotFound

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartIn(BaseModel):
    scenario_id: str


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def _sse(events: AsyncIterator[dict]) -> AsyncIterator[str]:
    async def gen() -> AsyncIterator[str]:
        async for ev in events:
            yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return gen()


@router.post("")
async def start_session(body: StartIn, c: ContainerDep, user: UserDep) -> dict:
    return await c.practice.start(user, body.scenario_id)


@router.get("")
async def list_sessions(c: ContainerDep, user: UserDep) -> list[dict]:
    return await c.practice.list_sessions(user)


@router.get("/{sid}")
async def get_session(sid: uuid.UUID, c: ContainerDep, user: UserDep) -> dict:
    return await c.practice.detail(sid, user)


@router.post("/{sid}/messages")
async def send_message(
    sid: uuid.UUID, body: MessageIn, c: ContainerDep, user: UserDep
) -> EventSourceResponse:
    """SSE 事件：token（客户回复片段）/ status / report_ready / error / done。"""
    events = await c.practice.open_message_stream(sid, user, body.text)
    return EventSourceResponse(_sse(events), headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{sid}/hint")
async def hint(sid: uuid.UUID, c: ContainerDep, user: UserDep) -> dict:
    return {"hint": await c.practice.hint(sid, user)}


@router.post("/{sid}/end")
async def end_session(sid: uuid.UUID, c: ContainerDep, user: UserDep) -> dict:
    return await c.practice.end(sid, user)


@router.get("/{sid}/report")
async def get_report(sid: uuid.UUID, c: ContainerDep, user: UserDep) -> dict:
    report = await c.practice.report(sid, user)
    if report is None:
        raise NotFound("报告尚未生成")
    return report
