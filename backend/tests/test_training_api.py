"""催收培训 HTTP 全链路集成测试（真实 PostgreSQL + Stub 模型 + Stub 录音转写）。

需设置 TEST_DATABASE_URL（测试库会被清空）。
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
def train_settings(tmp_path_factory) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_URL,
        llm={"provider": "stub"},
        admin_userids=["ADMIN1"],
        frontend_dist=tmp_path_factory.mktemp("nodist"),
    )


@pytest.fixture(scope="module")
def train_db(train_settings: Settings):
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
                "recording_questions, exam_attempts, exam_publications, knowledge_chunks RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


@pytest.fixture
async def client(train_settings: Settings, train_db):
    from app.main import create_app

    app = create_app(train_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
            yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _admin(client) -> dict:
    r = await client.post("/api/auth/dev", json={"userid": "ADMIN1", "name": "管理员", "department": "管理"})
    return _h(r.json()["token"])


async def _register_and_approve(client, admin: dict, userid: str) -> dict:
    r = await client.post(
        "/api/auth/register",
        json={"userid": userid, "name": "新人", "department": "催收", "password": "pass1234"},
    )
    assert r.status_code == 200 and r.json()["status"] == "pending"
    accounts = (await client.get("/api/admin/accounts?status=pending", headers=admin)).json()
    uid = next(a["id"] for a in accounts["items"] if a["userid"] == userid)
    r = await client.post(f"/api/admin/accounts/{uid}/review", json={"action": "approve"}, headers=admin)
    assert r.json()["status"] == "active"
    r = await client.post("/api/auth/login", json={"userid": userid, "password": "pass1234"})
    assert r.status_code == 200
    return _h(r.json()["token"])


async def test_register_review_login(client):
    cfg = (await client.get("/api/auth/config?redirect_uri=http://x/login")).json()
    assert cfg["password_enabled"] and cfg["register_enabled"] and cfg["require_approval"]

    body = {"userid": "N001", "name": "张三", "department": "催收", "password": "abc12345"}
    r = await client.post("/api/auth/register", json=body)
    assert r.json() == {"status": "pending", "message": "账号正在等待管理员审核，审核通过后即可登录"}
    assert (await client.post("/api/auth/register", json=body)).status_code == 409
    r = await client.post("/api/auth/login", json={"userid": "N001", "password": "abc12345"})
    assert r.status_code == 403 and "审核" in r.json()["message"]

    admin = await _admin(client)
    normal = (await client.post("/api/auth/dev", json={"userid": "U9", "name": "x"})).json()["token"]
    assert (await client.get("/api/admin/accounts", headers=_h(normal))).status_code == 403

    page = (await client.get("/api/admin/accounts?status=pending", headers=admin)).json()
    assert page["pending"] == 1 and page["items"][0]["userid"] == "N001"
    assert "password_hash" not in json.dumps(page)
    uid = page["items"][0]["id"]
    await client.post(f"/api/admin/accounts/{uid}/review", json={"action": "approve"}, headers=admin)

    assert (
        await client.post("/api/auth/login", json={"userid": "N001", "password": "wrong"})
    ).status_code == 401
    r = await client.post("/api/auth/login", json={"userid": "N001", "password": "abc12345"})
    token = r.json()["token"]
    assert r.json()["user"]["name"] == "张三" and not r.json()["user"]["is_admin"]

    r = await client.post(
        "/api/auth/password",
        json={"old_password": "abc12345", "new_password": "newpass99"},
        headers=_h(token),
    )
    assert r.json() == {"ok": True}
    assert (
        await client.post("/api/auth/login", json={"userid": "N001", "password": "newpass99"})
    ).status_code == 200

    # 停用后已签发的 token 立即失效
    await client.post(f"/api/admin/accounts/{uid}/review", json={"action": "disable"}, headers=admin)
    assert (await client.get("/api/auth/me", headers=_h(token))).status_code == 401

    # 设为管理员
    await client.post(f"/api/admin/accounts/{uid}/review", json={"action": "enable"}, headers=admin)
    await client.post(f"/api/admin/accounts/{uid}/role", json={"role": "admin"}, headers=admin)
    assert (await client.get("/api/auth/me", headers=_h(token))).json()["is_admin"]


async def test_publish_recording_with_reviewed_learning_content(client):
    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "N101")
    await client.post(
        "/api/admin/recordings",
        json={"audio_url": "https://oss.example.com/learning.mp3", "title": "学习录音"},
        headers=admin,
    )
    rows = (await client.get("/api/admin/recordings?q=学习录音", headers=admin)).json()["items"]
    rid = rows[0]["id"]
    path = f"/api/admin/recordings/{rid}"
    fields = {"extracted_scenario_ids": ["C08", "C08"], "learning_note": "留意如何确认当通行动。"}
    assert (await client.patch(path, json=fields, headers=user)).status_code == 403
    assert (await client.patch(path, json=fields, headers=admin)).status_code == 200
    assert (await client.get(f"/api/recordings/{rid}", headers=user)).status_code == 404

    response = await client.patch(path, json={"published": True}, headers=admin)
    assert response.status_code == 200
    recordings = (await client.get("/api/recordings?q=学习录音", headers=user)).json()
    detail = (await client.get(f"/api/recordings/{rid}", headers=user)).json()
    assert detail["learning_note"] == fields["learning_note"]
    assert [scenario["id"] for scenario in detail["extracted_scenarios"]] == ["C08"]
    assert recordings["items"][0]["extracted_scenarios"] == detail["extracted_scenarios"]
    assert (await client.get("/api/scenarios/C08", headers=user)).status_code == 200


async def test_dbmcp_import_reuses_recording_id_and_versions_transcript(client, monkeypatch):
    row = {
        "call_id": 8765432,
        "url": "https://oss.example.com/dbmcp.mp3",
        "characters": [{"ChannelId": 0, "BeginTime": 0, "EndTime": 1000, "Text": "请核对办理进度。"}],
    }

    async def fetch(cfg, limit, call_id):
        assert limit == 1 and call_id == row["call_id"]
        return [row]

    monkeypatch.setattr("app.services.recordings.fetch_recordings_with_transcripts", fetch)
    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "NDBMCP")
    route = "/api/admin/recordings/import-dbmcp"
    body = {"limit": 1, "call_id": row["call_id"]}
    assert (await client.post(route, headers=user, json=body)).status_code == 403
    usable = row["characters"]
    for invalid in (None, "[]", [{"ChannelId": 0, "BeginTime": 0, "EndTime": 1000, "Text": " "}]):
        row["characters"] = invalid
        skipped = (await client.post(route, headers=admin, json=body)).json()
        assert skipped["missing_transcript"] == 1 and skipped["created"] == skipped["linked"] == 0
    assert (await client.get("/api/admin/recordings?q=8765432", headers=admin)).json()["total"] == 0
    row["characters"] = usable
    first = (await client.post(route, headers=admin, json=body)).json()
    assert first["created"] == first["linked"] == 1
    existing = (await client.post(route, headers=admin, json=body)).json()
    assert existing["existing"] == existing["linked"] == 1 and existing["created"] == 0
    listing = "/api/admin/recordings?q=8765432"
    items = (await client.get(listing, headers=admin)).json()["items"]
    assert len(items) == 1 and not items[0]["published"]
    detail = f"/api/admin/recordings/{items[0]['id']}"
    snapshot = (await client.get(detail, headers=admin)).json()["transcript_snapshot_id"]
    row["characters"][0]["Text"] = "请核对处理时间。"
    assert (await client.post(route, headers=admin, json=body)).json()["existing"] == 1
    latest = (await client.get(detail, headers=admin)).json()
    assert latest["transcript_snapshot_id"] != snapshot
    assert latest["source_transcript"][0]["text"] == "请核对处理时间。"


async def test_recording_yaml_review_and_withdrawal(client):
    from uuid import uuid4

    from app.db.models import TranscriptSnapshot

    container = client._transport.app.state.container
    async with container.session_factory() as db, db.begin():
        snapshot = TranscriptSnapshot(
            source_key=f"recording-workflow-test:{uuid4()}",
            source_hash="a" * 64,
            source_file="测试录音",
            source_labels="还款困难",
            segments=[{"seq": 1, "channel": 1, "text": "客户：我现在有还款困难。"}],
            speaker_mapping={"1": "客户"},
            speaker_mapping_status="confirmed",
            time_unit="ms",
        )
        db.add(snapshot)
        await db.flush()
        snapshot_id = snapshot.id
    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "N102")
    await client.post(
        "/api/admin/recordings",
        headers=admin,
        json={"audio_url": "https://oss.example.com/workflow.mp3", "title": "生成场景的测试录音"},
    )
    rows = (await client.get("/api/admin/recordings?q=生成场景", headers=admin)).json()["items"]
    rid = rows[0]["id"]
    route = f"/api/admin/recordings/{rid}"
    assert (await client.post(f"{route}/process", headers=admin, json={})).status_code == 404
    assert (
        await client.patch(
            route, headers=admin, json={"transcript_snapshot_id": snapshot_id, "learning_note": "问清困难。"}
        )
    ).status_code == 200

    async def generate(existing_ids=()):
        response = await client.post(f"{route}/practices", headers=admin, json={"first": 1, "last": 1})
        assert response.status_code == 200, response.text
        return next(item for item in response.json()["practice_candidates"] if item["id"] not in existing_ids)

    accepted = await generate()
    archived = await generate({accepted["id"]})
    assert accepted["status"] == "pending" and "scoring:" in accepted["yaml"]
    sid = accepted["id"]
    assert (
        await client.patch(f"{route}/practices/{archived['id']}", headers=admin, json={"status": "archived"})
    ).status_code == 200
    assert (await client.get(f"/api/scenarios/{sid}", headers=user)).status_code == 404
    assert (await client.patch(route, headers=admin, json={"published": True})).status_code == 200
    detail = (await client.get(f"/api/recordings/{rid}", headers=user)).json()
    assert [item["id"] for item in detail["extracted_scenarios"]] == [sid]
    assert "source_transcript" not in detail and "practice_candidates" not in detail
    assert (await client.get(f"/api/scenarios/{archived['id']}", headers=user)).status_code == 404
    completed = (await client.post("/api/sessions", headers=user, json={"scenario_id": sid})).json()["id"]
    active = (await client.post("/api/sessions", headers=user, json={"scenario_id": sid})).json()["id"]
    assert (await client.post(f"/api/sessions/{completed}/end", headers=user)).status_code == 200
    assert (await client.patch(route, headers=admin, json={"published": False})).status_code == 200
    assert (await client.post("/api/sessions", headers=user, json={"scenario_id": sid})).status_code == 404
    assert (
        await client.post(f"/api/sessions/{active}/messages", headers=user, json={"text": "您好"})
    ).status_code == 409
    assert (await client.get(f"/api/sessions/{completed}/report", headers=user)).status_code == 200


async def _send(client, h, sid, text_: str) -> list[dict]:
    events = []
    async with client.stream("POST", f"/api/sessions/{sid}/messages", json={"text": text_}, headers=h) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def test_self_test_quiz(client):
    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "N200")
    papers = (await client.get("/api/exams", headers=user)).json()
    assert "T02" not in {p["id"] for p in papers}
    a = (await client.post("/api/exams/T01/start", headers=user)).json()
    items = a["sections"][0]["items"]
    assert len(items) == 10 and "answer" not in items[0] and not a["revealed"]
    # 重复开始返回同一份进行中的卷子
    assert (await client.post("/api/exams/T01/start", headers=user)).json()["id"] == a["id"]

    r = await client.put(
        f"/api/exams/attempts/{a['id']}/answers",
        json={"answers": {it["key"]: [0] for it in items} | {"q:NOPE": [1]}},
        headers=user,
    )
    assert r.json() == {"saved": 10}
    other = await _register_and_approve(client, admin, "N201")
    assert (await client.get(f"/api/exams/attempts/{a['id']}", headers=other)).status_code == 403

    res = (await client.post(f"/api/exams/attempts/{a['id']}/submit", headers=user)).json()
    assert res["status"] == "submitted" and res["revealed"] and res["result"]["total"] == res["score"]
    assert "answer" in res["sections"][0]["items"][0] and "credit" in res["sections"][0]["items"][0]
    r = await client.put(f"/api/exams/attempts/{a['id']}/answers", json={"answers": {}}, headers=user)
    assert r.status_code == 409
    # 自测不限次
    assert (await client.post("/api/exams/T01/start", headers=user)).json()["id"] != a["id"]


async def test_formal_exam_with_roleplay(client):
    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "N300")
    assert (await client.post("/api/exams/E01/start", headers=user)).status_code == 404
    assert (await client.post("/api/admin/exams/papers/E01/publish", headers=user)).status_code == 403
    assert (await client.post("/api/admin/exams/papers/E01/publish", headers=admin)).status_code == 200
    a = (await client.post("/api/exams/E01/start", headers=user)).json()
    types = [s["type"] for s in a["sections"]]
    assert types == ["quiz", "roleplay"]
    assert a["deadline_at"]
    quiz = a["sections"][0]["items"]
    await client.put(
        f"/api/exams/attempts/{a['id']}/answers", json={"answers": {quiz[0]["key"]: [0]}}, headers=user
    )
    refreshed = (await client.get(f"/api/exams/attempts/{a['id']}", headers=user)).json()
    assert refreshed["sections"][0]["items"][0]["chosen"] == [0]

    rp = a["sections"][1]["items"]
    assert len(rp) == 2
    sid = (
        await client.post(f"/api/exams/attempts/{a['id']}/roleplay", json={"key": rp[0]["key"]}, headers=user)
    ).json()["session_id"]
    again = await client.post(
        f"/api/exams/attempts/{a['id']}/roleplay", json={"key": rp[0]["key"]}, headers=user
    )
    assert again.json()["session_id"] == sid
    s = (await client.get(f"/api/sessions/{sid}", headers=user)).json()
    assert s["mode"] == "exam" and s["exam_attempt_id"] == a["id"]
    assert (await client.post(f"/api/sessions/{sid}/hint", headers=user)).status_code == 403

    await _send(
        client, user, sid, "您好，我是贷后服务中心的，工号 1024，请问是本人吗？方便说说最近的情况吗？"
    )

    # 交卷：进行中的对练自动结束并出报告；第二场未开始计 0 分
    res = (await client.post(f"/api/exams/attempts/{a['id']}/submit", headers=user)).json()
    assert res["status"] == "submitted" and res["revealed"]
    rp_items = res["sections"][1]["items"]
    assert rp_items[0]["report_ready"] and rp_items[0]["score"] is not None
    assert rp_items[1]["session_id"] is None
    assert res["result"]["sections"][1]["score"] == round(rp_items[0]["score"] / 2, 1)
    assert res["passed"] is False
    repeated = (await client.post(f"/api/exams/attempts/{a['id']}/submit", headers=user)).json()
    assert repeated["submitted_at"] == res["submitted_at"] and repeated["result"] == res["result"]

    # 限次：E01 最多 3 次
    for _ in range(2):
        b = (await client.post("/api/exams/E01/start", headers=user)).json()
        await client.post(f"/api/exams/attempts/{b['id']}/submit", headers=user)
    r = await client.post("/api/exams/E01/start", headers=user)
    assert r.status_code == 403 and "3 次" in r.json()["message"]
    card = next(p for p in (await client.get("/api/exams", headers=user)).json() if p["id"] == "E01")
    assert card["attempts"] == 3 and card["best_score"] is not None

    page = (await client.get("/api/admin/exams/attempts?paper_id=E01", headers=admin)).json()
    assert page["total"] == 3 and page["items"][0]["user"]["userid"] == "N300"
    d = (await client.get(f"/api/admin/exams/attempts/{a['id']}", headers=admin)).json()
    assert d["revealed"] and d["sections"][0]["items"][0]["answer"]
    papers = (await client.get("/api/admin/exams/papers", headers=admin)).json()
    assert {p["id"] for p in papers} >= {"E01", "T01"}


async def test_exam_deadline_auto_submit(client, train_settings):
    from datetime import UTC, datetime, timedelta

    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "N400")
    a = (await client.post("/api/exams/T03/start", headers=user)).json()
    engine = create_engine(TEST_URL)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE exam_attempts SET deadline_at = :d WHERE id = :i"),
            {"d": datetime.now(UTC) - timedelta(minutes=5), "i": a["id"]},
        )
    engine.dispose()
    r = await client.put(f"/api/exams/attempts/{a['id']}/answers", json={"answers": {}}, headers=user)
    assert r.status_code == 409
    v = (await client.get(f"/api/exams/attempts/{a['id']}", headers=user)).json()
    assert v["status"] == "submitted" and v["score"] == 0


async def test_publication_pins_scenario_and_rubric_through_scoring_retry(client, monkeypatch):
    from app.core.errors import UpstreamError

    app = client._transport.app
    container = app.state.container
    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "N510")
    other = await _register_and_approve(client, admin, "N511")
    publish = "/api/admin/exams/papers/E01/publish"
    assert (await client.post(publish, headers=admin)).status_code == 200
    scenario = container.scenarios.get("C08")
    old_rubric = container.scenarios.rubric_for(scenario)
    monkeypatch.setitem(container.scenarios.scenarios, "C08", scenario.model_copy(update={"name": "新版本"}))
    monkeypatch.setitem(
        container.scenarios.rubrics, old_rubric.id, old_rubric.model_copy(update={"name": "新评分表"})
    )
    old = (await client.post("/api/exams/E01/start", headers=user)).json()
    assert old["sections"][1]["items"][0]["scenario_name"] == scenario.name
    assert "scenario_snapshot" not in old["sections"][1]["items"][0]

    assert (await client.post(publish, headers=admin)).status_code == 200
    new = (await client.post("/api/exams/E01/start", headers=other)).json()
    assert new["sections"][1]["items"][0]["scenario_name"] == "新版本"
    assert (await client.post("/api/exams/E01/start", headers=user)).json()["id"] == old["id"]

    aid = old["id"]
    roleplay = f"/api/exams/attempts/{aid}/roleplay"
    opened = await asyncio.gather(
        *[client.post(roleplay, json={"key": "s:C08"}, headers=user) for _ in range(2)]
    )
    assert opened[0].json() == opened[1].json()
    sid = opened[0].json()["session_id"]
    detail = (await client.get(f"/api/sessions/{sid}", headers=user)).json()
    assert detail["scenario_name"] == scenario.name
    await _send(client, user, sid, "您先别急，我想了解一下您目前遇到的困难。")

    structured = container.llm.structured

    async def fail_once(purpose, *args, **kwargs):
        if purpose == "coach":
            monkeypatch.setattr(container.llm, "structured", structured)
            raise UpstreamError("模拟评分失败")
        return await structured(purpose, *args, **kwargs)

    monkeypatch.setattr(container.llm, "structured", fail_once)
    submit = f"/api/exams/attempts/{aid}/submit"
    failed = await client.post(submit, headers=user)
    assert failed.status_code == 400 and failed.json()["message"] == "模拟评分失败"
    assert (await client.get(f"/api/exams/attempts/{aid}", headers=user)).json()["status"] == "in_progress"
    assert (await client.post(submit, headers=user)).json()["status"] == "submitted"
    report = (await client.get(f"/api/sessions/{sid}/report", headers=user)).json()
    assert report["rubric"] == old_rubric.name
