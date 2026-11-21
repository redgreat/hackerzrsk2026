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
        recordings={"asr_provider": "stub"},
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
                "recording_questions, exam_attempts, knowledge_chunks RESTART IDENTITY CASCADE"
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


async def _wait_ready(client, admin, rid: int) -> dict:
    for _ in range(50):
        d = (await client.get(f"/api/admin/recordings/{rid}", headers=admin)).json()
        if d["status"] in ("ready", "failed"):
            return d
        await asyncio.sleep(0.1)
    raise AssertionError("录音处理超时")


async def test_recording_pipeline_and_learning(client):
    admin = await _admin(client)
    user = await _register_and_approve(client, admin, "N100")

    r = await client.post(
        "/api/admin/recordings",
        json={"audio_url": "https://oss.example.com/a.mp3", "title": ""},
        headers=admin,
    )
    assert r.json() == {"created": 1}
    rid = (await client.get("/api/admin/recordings", headers=admin)).json()["items"][0]["id"]

    # 未处理不能发布；员工看不到
    r = await client.patch(f"/api/admin/recordings/{rid}", json={"published": True}, headers=admin)
    assert r.status_code == 400
    assert (await client.get("/api/recordings", headers=user)).json()["total"] == 0

    await client.post(f"/api/admin/recordings/{rid}/process", json={}, headers=admin)
    d = await _wait_ready(client, admin, rid)
    assert d["status"] == "ready", d["error"]
    assert d["transcript"][0]["speaker"] == "agent"
    full_text = "".join(t["text"] for t in d["transcript"])
    assert "13812345678" not in full_text and "建国" not in full_text
    assert d["analysis"]["highlights"] and d["customer_type"] == "忘记还款"
    assert d["analysis"]["related_scenario_ids"] == ["C01"]
    assert len(d["questions"]) == 2 and all(q["status"] == "pending" for q in d["questions"])

    q1, q2 = d["questions"]
    r = await client.patch(
        f"/api/admin/recording-questions/{q1['id']}", json={"status": "approved"}, headers=admin
    )
    assert r.json()["status"] == "approved"
    r = await client.patch(f"/api/admin/recording-questions/{q2['id']}", json={"answer": [5]}, headers=admin)
    assert r.status_code == 400

    r = await client.patch(
        f"/api/admin/recordings/{rid}", json={"published": True, "title": "首逾提醒示范"}, headers=admin
    )
    assert r.json()["published"] and r.json()["title"] == "首逾提醒示范"

    lst = (await client.get("/api/recordings", headers=user)).json()
    assert lst["total"] == 1 and lst["customer_types"] == [{"name": "忘记还款", "count": 1}]
    detail = (await client.get(f"/api/recordings/{rid}", headers=user)).json()
    assert detail["audio_url"] and detail["related_scenarios"][0]["id"] == "C01"
    assert [q["id"] for q in detail["questions"]] == [q1["id"]]
    assert "answer" not in detail["questions"][0]

    r = await client.post(
        f"/api/recordings/{rid}/questions/{q1['id']}/check", json={"answer": [1]}, headers=user
    )
    assert r.json()["correct"] and r.json()["explanation"]
    r = await client.post(
        f"/api/recordings/{rid}/questions/{q2['id']}/check", json={"answer": [0]}, headers=user
    )
    assert r.status_code == 404  # 未审核题目不可作答
    await client.post(f"/api/recordings/{rid}/played", headers=user)

    # 发布后亮点话术进入知识库；取消发布即移除
    kn = (await client.get("/api/admin/knowledge", headers=admin)).json()
    assert any(k["source"] == f"recording:{rid}" for k in kn)
    await client.patch(f"/api/admin/recordings/{rid}", json={"published": False}, headers=admin)
    kn = (await client.get("/api/admin/knowledge", headers=admin)).json()
    assert not any(k["source"] == f"recording:{rid}" for k in kn)
    assert (await client.get(f"/api/recordings/{rid}", headers=user)).status_code == 404
    await client.patch(f"/api/admin/recordings/{rid}", json={"published": True}, headers=admin)

    usage = (await client.get("/api/admin/usage?purpose=analyst", headers=admin)).json()
    assert usage["total"] >= 1


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
    assert papers[0]["kind"] == "exam"
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
    a = (await client.post("/api/exams/E01/start", headers=user)).json()
    types = [s["type"] for s in a["sections"]]
    # 听录音部分依赖已发布录音的已审核题目（上一条测试已准备 1 道）
    assert types == ["quiz", "listening", "roleplay"]
    assert a["deadline_at"] and a["sections"][1]["items"][0]["recording"]["audio_url"]
    quiz = a["sections"][0]["items"]
    await client.put(
        f"/api/exams/attempts/{a['id']}/answers", json={"answers": {quiz[0]["key"]: [0]}}, headers=user
    )

    rp = a["sections"][2]["items"]
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
    rp_items = res["sections"][2]["items"]
    assert rp_items[0]["report_ready"] and rp_items[0]["score"] is not None
    assert rp_items[1]["session_id"] is None
    assert res["result"]["sections"][2]["score"] == round(rp_items[0]["score"] / 2, 1)
    assert res["passed"] is False

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
