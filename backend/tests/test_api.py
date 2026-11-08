"""HTTP 全链路集成测试（真实 PostgreSQL + Stub 模型）。

需设置 TEST_DATABASE_URL（测试库会被清空），例如：
  TEST_DATABASE_URL=postgresql+psycopg://coach:coach@127.0.0.1:5432/ai_coach_test
"""

import json
import os

import httpx
import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="未设置 TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def api_settings(tmp_path_factory) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_URL,
        llm={"provider": "stub"},
        speech={"asr_provider": "stub", "tts_provider": "stub"},
        frontend_dist=tmp_path_factory.mktemp("nodist"),
    )


@pytest.fixture(scope="module")
def prepared_db(api_settings: Settings):
    from alembic import command
    from alembic.config import Config

    from app.cli import _run, _setup_langgraph
    from app.core.config import BACKEND_DIR

    os.environ["DATABASE_URL"] = TEST_URL
    from app.core.config import get_settings

    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    _run(_setup_langgraph())
    engine = create_engine(TEST_URL)
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE users, practice_sessions, practice_messages, model_usage RESTART IDENTITY CASCADE")
        )
    engine.dispose()


@pytest.fixture
async def client(api_settings: Settings, prepared_db):
    from app.main import create_app

    app = create_app(api_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
            yield c


async def _login(client, userid: str) -> dict:
    r = await client.post("/api/auth/dev", json={"userid": userid, "name": "测试员", "department": "销售"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _send(client, h, sid, text_: str) -> list[dict]:
    events = []
    async with client.stream("POST", f"/api/sessions/{sid}/messages", json={"text": text_}, headers=h) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def test_full_practice_flow(client):
    assert (await client.get("/api/health")).json()["status"] == "ok"
    assert (await client.get("/api/scenarios")).status_code == 401
    h = await _login(client, "T001")

    cards = (await client.get("/api/scenarios", headers=h)).json()
    assert cards[0]["department"] == ["销售"]
    detail = (await client.get("/api/scenarios/S01", headers=h)).json()
    assert "objections" not in json.dumps(detail) and "hidden_needs" not in json.dumps(detail)

    s = (await client.post("/api/sessions", json={"scenario_id": "S01"}, headers=h)).json()
    sid = s["id"]
    assert s["messages"][0]["role"] == "customer"
    assert "inner_thought" not in s["messages"][0]

    events = await _send(client, h, sid, "王经理您好，理解您关注价格，方便说说您主要在对比哪些方面吗？")
    assert any(e["type"] == "token" for e in events)
    assert events[-1] == {"type": "done", "status": "ongoing", "turn": 1}

    hint = (await client.post(f"/api/sessions/{sid}/hint", headers=h)).json()["hint"]
    assert hint

    other = await _login(client, "T002")
    assert (await client.get(f"/api/sessions/{sid}", headers=other)).status_code == 403

    report = (await client.post(f"/api/sessions/{sid}/end", headers=h)).json()
    assert report["outcome"] == "user_end" and report["total_score"] > 0
    assert (await client.post(f"/api/sessions/{sid}/end", headers=h)).json() == report

    r = await client.post(f"/api/sessions/{sid}/messages", json={"text": "还在吗"}, headers=h)
    assert r.status_code == 409

    d = (await client.get(f"/api/sessions/{sid}", headers=h)).json()
    assert [m["role"] for m in d["messages"]] == ["customer", "user", "customer", "hint"]
    assert d["messages"][1]["inner_thought"]
    assert d["hints_used"] == 1 and d["cost_yuan"] >= 0

    asr = await client.post(
        "/api/speech/asr",
        headers=h,
        files={"file": ("a.webm", b"xx", "audio/webm")},
        data={"duration_ms": "3000", "session_id": sid},
    )
    assert asr.json()["text"]

    assert len((await client.get("/api/sessions", headers=h)).json()) == 1
    me = (await client.get("/api/stats/me", headers=h)).json()
    assert me["practice_count"] == 1 and len(me["dimension_avg"]) == 6
    ov = (await client.get("/api/stats/overview", headers=h)).json()
    assert ov["finished_sessions"] == 1
    purposes = {p["purpose"] for p in ov["by_purpose"]}
    assert {"customer", "evaluator", "hint", "coach", "asr"} <= purposes
