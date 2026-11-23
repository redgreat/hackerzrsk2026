"""陪练服务的流式执行及异常锁释放回归测试，不依赖数据库。"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langgraph.types import Command

from app.core.errors import Conflict
from app.services.practice import PracticeService


async def test_service_stream_and_report(graph, ctx):
    service = PracticeService(graph, ctx, None)
    service._persist = AsyncMock()
    sid = uuid.uuid4()
    user = SimpleNamespace(id=1)
    await service._run_command(sid, user, {"session_id": str(sid), "user_id": "u1", "scenario_id": "S01"})
    events = []

    async def sink(event):
        events.append(event)

    lock = await service._acquire_input(sid)
    await service._run_locked(
        sid, user, Command(resume={"type": "message", "text": "您好，方便介绍一下您的需求吗？"}), lock, sink
    )
    assert any(e["type"] == "token" and e["text"] for e in events)
    assert events[-1]["type"] == "done"
    assert not lock.locked()

    values = await service._run_command(sid, user, Command(resume={"type": "end"}))
    assert values["report"]["outcome"] == "user_end"
    assert service._persist.await_count == 3


@pytest.mark.parametrize("error", [RuntimeError("读取状态失败"), asyncio.CancelledError()])
async def test_input_state_failure_releases_lock(graph, ctx, error):
    service = PracticeService(graph, ctx, None)
    service._next_nodes = AsyncMock(side_effect=error)
    sid = uuid.uuid4()
    with pytest.raises(type(error)):
        await service._acquire_input(sid)
    assert not service._locks[sid].locked()


async def test_finished_session_releases_lock(graph, ctx):
    service = PracticeService(graph, ctx, None)
    service._next_nodes = AsyncMock(return_value=())
    sid = uuid.uuid4()
    with pytest.raises(Conflict):
        await service._acquire_input(sid)
    assert not service._locks[sid].locked()
