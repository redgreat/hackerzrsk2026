"""HTTP 全链路集成测试（真实 PostgreSQL + Stub 模型）。

需设置 TEST_DATABASE_URL（测试库会被清空），例如：
  TEST_DATABASE_URL=postgresql+psycopg://coach:coach@127.0.0.1:5432/ai_coach_test
"""

import base64
import json
import os

import httpx
import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings

TEST_URL = os.getenv("TEST_DATABASE_URL")
WECOM_TOKEN = "testtoken"
WECOM_AES_KEY = base64.b64encode(os.urandom(32)).decode().rstrip("=")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="未设置 TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def api_settings(tmp_path_factory, test_scenarios_dir) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_URL,
        scenarios_dir=test_scenarios_dir,
        llm={"provider": "stub"},
        speech={"asr_provider": "stub", "tts_provider": "stub"},
        admin_userids=["T001"],
        wecom={
            "corp_id": "wwtestcorp",
            "agent_id": "1000002",
            "secret": "s",
            "token": WECOM_TOKEN,
            "encoding_aes_key": WECOM_AES_KEY,
            "public_base_url": "https://coach.test",
        },
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
            text("TRUNCATE users, practice_sessions, practice_messages, model_usage, recordings RESTART IDENTITY CASCADE")
        )
        conn.execute(
            text("""
            INSERT INTO recordings (source, source_key, audio_url, title, status, tags, customer_type, published, play_count, meta)
            VALUES ('file', 'api-test-recording', 'https://example.test/audio.mp3', '测试录音',
                'ready', '{}', '', true, 0, '{"extracted_scenario_ids":["S01"]}'::jsonb)
            ON CONFLICT (source_key) DO NOTHING
        """)
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
    r = await client.post("/api/auth/dev", json={"userid": userid, "name": "测试员", "department": "客服"})
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
    assert cards[0]["department"] == ["客服", "服务"]
    detail = (await client.get("/api/scenarios/S01", headers=h)).json()
    assert "objections" not in json.dumps(detail) and "hidden_needs" not in json.dumps(detail)
    assert detail["source_recording"]["title"] == "测试录音"
    assert all(card["id"] != "S03" for card in cards)
    assert (await client.get("/api/scenarios/S03", headers=h)).status_code == 404
    assert (await client.post("/api/sessions", json={"scenario_id": "S03"}, headers=h)).status_code == 404

    s = (await client.post("/api/sessions", json={"scenario_id": "S01"}, headers=h)).json()
    sid = s["id"]
    assert s["messages"][0]["role"] == "customer"
    assert "inner_thought" not in s["messages"][0]

    events = await _send(
        client,
        h,
        sid,
        "赵女士，非常抱歉让您久等了。我先确认一下昨天故障的时间和您现在最着急解决的问题，可以吗？",
    )
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
    assert me["practice_count"] == 1 and len(me["dimension_avg"]) == 5
    assert (await client.get("/api/admin/overview", headers=other)).status_code == 403
    ov = (await client.get("/api/admin/overview", headers=h)).json()
    assert ov["finished_sessions"] == 1
    purposes = {p["purpose"] for p in ov["by_purpose"]}
    assert {"customer", "evaluator", "hint", "coach", "asr"} <= purposes


def _wecom_envelope(inner_xml: str, bad_sig: bool = False) -> tuple[str, str]:
    from app.services import wecom_crypto as crypto

    enc = crypto.encrypt(WECOM_AES_KEY, inner_xml, "wwtestcorp")
    ts, nonce = "1700000000", "nonce1"
    sig = "bad" if bad_sig else crypto._sha1(WECOM_TOKEN, ts, nonce, enc)
    body = f"<xml><ToUserName>wwtestcorp</ToUserName><Encrypt><![CDATA[{enc}]]></Encrypt></xml>"
    return f"/api/wecom/callback?msg_signature={sig}&timestamp={ts}&nonce={nonce}", body


def _msg(userid: str, msg_type: str, body: str, msg_id: str) -> str:
    field = "Recognition" if msg_type == "voice" else "Content"
    return (
        f"<xml><ToUserName>wwtestcorp</ToUserName><FromUserName>{userid}</FromUserName>"
        f"<MsgType>{msg_type}</MsgType><MsgId>{msg_id}</MsgId><{field}>{body}</{field}></xml>"
    )


async def test_wecom_callback_chat_flow(client, monkeypatch):
    from app.services.wecom import WeComClient

    sent: list[tuple[str, str]] = []
    links: list[str] = []

    async def fake_text(self, userid, text):
        sent.append((userid, text))

    async def fake_link(self, userid, title, desc, url):
        links.append(url)

    monkeypatch.setattr(WeComClient, "send_text", fake_text)
    monkeypatch.setattr(WeComClient, "send_link_card", fake_link)

    url = "/api/wecom/callback"
    r = await client.get(f"{url}?msg_signature=x&timestamp=1&nonce=n&echostr=")
    assert r.status_code == 401  # 签名错误
    from app.services import wecom_crypto as crypto

    enc = crypto.encrypt(WECOM_AES_KEY, "123456", "wwtestcorp")
    sig = crypto._sha1(WECOM_TOKEN, "1", "n", enc)
    r = await client.get(url, params={"msg_signature": sig, "timestamp": "1", "nonce": "n", "echostr": enc})
    assert r.status_code == 200 and r.text == "123456"

    path, body = _wecom_envelope(_msg("W100", "text", "1", "m1"), bad_sig=True)
    assert (await client.post(path, content=body)).status_code == 401

    path, body = _wecom_envelope(_msg("W100", "text", "1", "m1"))
    assert (await client.post(path, content=body)).text == "success"
    assert "【情绪激动的投诉客户】" in sent[-1][1] and "赵女士" in sent[-1][1]

    path, body = _wecom_envelope(_msg("W100", "text", "1", "m1"))  # 重复投递应去重
    await client.post(path, content=body)
    assert sum("【情绪激动的投诉客户】" in t for _, t in sent) == 1

    path, body = _wecom_envelope(
        _msg(
            "W100",
            "text",
            "赵女士，非常抱歉让您久等了。我先确认故障时间和您现在最着急解决的问题，可以吗？",
            "m2",
        )
    )
    await client.post(path, content=body)
    assert sent[-1][1].startswith("赵女士：")

    path, body = _wecom_envelope(_msg("W100", "voice", "求助", "m3"))
    await client.post(path, content=body)
    assert sent[-1][1].startswith("教练提示：")

    path, body = _wecom_envelope(_msg("W100", "voice", "", "m4"))
    await client.post(path, content=body)
    assert "没有识别到语音" in sent[-1][1]

    path, body = _wecom_envelope(_msg("W100", "text", "结束", "m5"))
    await client.post(path, content=body)
    assert any("本次得分" in t for _, t in sent)
    h = await _login(client, "W100")
    sid = (await client.get("/api/sessions", headers=h)).json()[0]["id"]
    assert links == [f"https://coach.test/report/{sid}"]

    path, body = _wecom_envelope(_msg("W100", "text", "报告", "m6"))
    await client.post(path, content=body)
    assert "这是你最近一次练习的报告" in sent[-1][1]


async def test_admin_endpoints(client):
    h = await _login(client, "T001")
    other = await _login(client, "T002")
    for path in [
        "/api/admin/users?q=T",
        "/api/admin/sessions?status=user_end",
        "/api/admin/usage?size=5",
        "/api/admin/scenarios",
        "/api/admin/knowledge",
        "/api/admin/trend?days=30",
    ]:
        assert (await client.get(path, headers=other)).status_code == 403, path
        r = await client.get(path, headers=h)
        assert r.status_code == 200, (path, r.text)
    users = (await client.get("/api/admin/users?q=T", headers=h)).json()
    assert users["total"] >= 1 and users["items"][0]["userid"].startswith("T")
    sess = (await client.get("/api/admin/sessions?size=50", headers=h)).json()
    assert sess["total"] >= 1
    detail = (await client.get(f"/api/admin/sessions/{sess['items'][0]['id']}", headers=h)).json()
    assert detail["messages"] and detail["usage"]
    assert (
        await client.get("/api/admin/sessions/00000000-0000-0000-0000-000000000000", headers=h)
    ).status_code == 404
    usage = (await client.get("/api/admin/usage?purpose=coach", headers=h)).json()
    assert usage["total"] >= 1 and all(r["purpose"] == "coach" for r in usage["items"])
    assert isinstance((await client.get("/api/admin/knowledge", headers=h)).json(), list)


async def test_publish_rubric_without_changing_open_session(client):
    admin = await _login(client, "T001")
    employee = await _login(client, "T002")
    path = "/api/admin/rubric"
    assert (await client.get(path, headers=employee)).status_code == 403
    initial = (await client.get(path, headers=admin)).json()["versions"][0]

    # S01 是测试示例，改为使用和录音练习相同的贷后评分表。
    app = client._transport.app
    scene = app.state.container.scenarios.scenarios["S01"]
    scene.scoring = initial["rubric"]["id"]
    old = (await client.post("/api/sessions", json={"scenario_id": "S01"}, headers=employee)).json()
    body = {**initial["rubric"], "name": "新版贷后评分", "base_version": initial["version"]}
    response = await client.post(path, headers=admin, json=body)
    assert response.json() == {"version": initial["version"] + 1}
    try:
        assert (await client.post(path, headers=admin, json=body)).status_code == 409
        detail = await client.get("/api/scenarios/S01", headers=employee)
        assert detail.json()["rubric"]["name"] == body["name"]
        report = await client.post(f"/api/sessions/{old['id']}/end", headers=employee)
        assert report.json()["rubric"] == initial["rubric"]["name"]
    finally:
        await client.post(path, headers=admin, json={**initial["rubric"], "base_version": initial["version"] + 1})
