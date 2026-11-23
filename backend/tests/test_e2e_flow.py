"""端到端流程：URL 导入 → 后台处理录音 → 管理员发布 → H5 列表可见 → 语音练习（stub 转写）→ 求助 → 结束出报告 → 日志表可查。

需要 TEST_DATABASE_URL（测试库会被清空）。全部外部服务使用 stub，不访问真实模型。
"""

import asyncio
import json
import os

import httpx
import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="未设置 TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def e2e_settings(tmp_path_factory) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_URL,
        llm={"provider": "stub"},
        speech={"asr_provider": "stub", "tts_provider": "stub"},
        recordings={"asr_provider": "stub", "audio_base_url": "https://oss.example.com"},
        admin_userids=["ADM1"],
        frontend_dist=tmp_path_factory.mktemp("nodist"),
    )


@pytest.fixture(scope="module")
def prepared(e2e_settings: Settings):
    from alembic import command
    from alembic.config import Config

    from app.cli import _run, _setup_langgraph
    from app.core.config import BACKEND_DIR, get_settings

    os.environ["DATABASE_URL"] = TEST_URL
    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    _run(_setup_langgraph())
    engine = create_engine(TEST_URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE users, practice_sessions, practice_messages, model_usage, recordings, "
                "recording_questions, exam_attempts, app_logs, app_settings RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


@pytest.fixture
async def client(e2e_settings: Settings, prepared):
    from app.main import create_app

    app = create_app(e2e_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
            yield c


async def _dev_login(client, userid: str) -> dict:
    r = await client.post("/api/auth/dev", json={"userid": userid, "name": userid, "department": "催收"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _wait_status(client, h, rid: int, want: set[str], seconds: float = 30) -> dict:
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        d = (await client.get(f"/api/admin/recordings/{rid}", headers=h)).json()
        if d["status"] in want or asyncio.get_running_loop().time() > deadline:
            return d
        await asyncio.sleep(0.3)


async def test_recording_to_practice_flow(client, e2e_settings):
    admin = await _dev_login(client, "ADM1")
    staff = await _dev_login(client, "STAFF1")

    # 1. 导入：经 CLI 同样的逻辑，这里直接调用服务层
    from app.services.recording_source import parse_lines
    from app.services.recordings import RecordingService

    items = parse_lines(
        "amp-prod/recall/a.mp3\t测试录音\nhttps://oss.example.com/b.mp3\n", e2e_settings.recordings
    )
    assert len(items) == 2
    svc: RecordingService = client._transport.app.state.container.recordings
    created, skipped = await svc.import_items(items, "url")
    assert (created, skipped) == (2, 0)
    assert (await svc.import_items(items, "url")) == (0, 2)  # 重复导入跳过

    # 2. 后台处理：stub 转写 → 分析 → ready；未发布前员工列表为空
    listing = (await client.get("/api/admin/recordings?size=10", headers=admin)).json()
    rid = listing["items"][0]["id"]
    r = await client.post(f"/api/admin/recordings/{rid}/process", json={"force": False}, headers=admin)
    assert r.status_code == 200 and r.json()["accepted"] is True
    d = await _wait_status(client, admin, rid, {"ready", "failed"})
    assert d["status"] == "ready", d.get("error")
    assert (await client.get("/api/recordings", headers=staff)).json()["items"] == []

    # 3. 管理员发布 → 员工列表可见，详情可读
    r = await client.patch(f"/api/admin/recordings/{rid}", json={"published": True}, headers=admin)
    assert r.status_code == 200, r.text
    listed = (await client.get("/api/recordings", headers=staff)).json()
    assert listed["items"] and listed["items"][0]["id"] == rid
    assert (await client.get(f"/api/recordings/{rid}", headers=staff)).status_code == 200

    # 4. 语音练习：stub ASR 转写 → 发消息 → 求助 → 结束出报告
    r = await client.post("/api/sessions", json={"scenario_id": "S01"}, headers=staff)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    asr = await client.post(
        "/api/speech/asr",
        headers=staff,
        files={"file": ("v.webm", b"xx", "audio/webm")},
        data={"duration_ms": "3000", "session_id": sid},
    )
    assert asr.status_code == 200 and asr.json()["text"]
    async with client.stream(
        "POST", f"/api/sessions/{sid}/messages", json={"text": asr.json()["text"]}, headers=staff
    ) as resp:
        assert resp.status_code == 200
        events = [json.loads(ln[6:]) async for ln in resp.aiter_lines() if ln.startswith("data: ")]
    assert events[-1]["type"] == "done"
    assert (await client.post(f"/api/sessions/{sid}/hint", headers=staff)).status_code == 200
    report = (await client.post(f"/api/sessions/{sid}/end", headers=staff)).json()
    assert report["total_score"] >= 0 and report["dimension_scores"]

    # 5. 应用日志表：本流程不应产生 ERROR 级别记录
    await asyncio.sleep(1.5)  # 等后台写库线程
    engine = create_engine(TEST_URL)
    with engine.connect() as conn:
        errors = conn.execute(
            text("SELECT count(*) FROM app_logs WHERE level IN ('ERROR','CRITICAL')")
        ).scalar()
    engine.dispose()
    assert errors == 0
