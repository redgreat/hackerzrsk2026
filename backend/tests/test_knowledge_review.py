"""独立存储测试库验证权限、人工修订、版本冲突及审核历史。"""

import os

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import KnowledgeEvent, TranscriptSnapshot
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.services.transcripts import ImportBatch, import_batch
from tests.test_transcripts import sample

pytestmark = pytest.mark.skipif(not os.getenv("TEST_TRANSCRIPT_DATABASE_URL"), reason="未设置独立存储测试库")


async def test_admin_review_flow_and_access_control():
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=os.environ["TEST_TRANSCRIPT_DATABASE_URL"],
        admin_userids=["review-admin"],
        llm={"provider": "stub"},
    )
    engine = create_engine(settings)
    sf = create_session_factory(engine)
    batch = ImportBatch.model_validate(sample())
    try:
        await import_batch(sf, batch)
        async with sf() as db:
            eid = await db.scalar(
                select(KnowledgeEvent.id)
                .join(TranscriptSnapshot)
                .where(TranscriptSnapshot.source_key == batch.cases[0].case_key)
            )
        app = create_app(settings)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
        ):
            path = f"/api/admin/knowledge-events/{eid}"
            assert (await client.get(path)).status_code == 401

            async def login(userid):
                r = await client.post("/api/auth/dev", json={"userid": userid})
                return {"Authorization": "Bearer " + r.json()["token"]}

            user, admin = await login("review-user"), await login("review-admin")
            assert (await client.get(path, headers=user)).status_code == 403
            assert (await client.get("/api/admin/knowledge-events", headers=user)).status_code == 403
            d = (await client.get(path, headers=admin)).json()
            body = {"action": "save", "expected_revision": 0, "data": d["data"], "note": "人工修订测试"}
            body["data"]["summary"] = "修改后的总结"
            assert (await client.post(path + "/review", json=body, headers=user)).status_code == 403
            r = await client.post(path + "/review", json=body, headers=admin)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["data"]["summary"] == "修改后的总结"
            assert d["original"]["summary"] != d["data"]["summary"]
            assert d["revision"] == 1 and d["status"] == "pending"
            assert (await client.post(path + "/review", json=body, headers=admin)).status_code == 409
            body.update(action="approve", expected_revision=1)
            d = (await client.post(path + "/review", json=body, headers=admin)).json()
            assert d["status"] == "approved" and not d["retrieval_enabled"]
            body.update(action="reject", expected_revision=2, note="")
            assert (await client.post(path + "/review", json=body, headers=admin)).status_code == 400
            body["note"] = "依据不足"
            d = (await client.post(path + "/review", json=body, headers=admin)).json()
            assert d["status"] == "rejected" and len(d["history"]) == 3
            body.update(action="save", expected_revision=3)
            d = (await client.post(path + "/review", json=body, headers=admin)).json()
            assert d["status"] == "pending" and len(d["history"]) == 4
            assert (await client.get("/api/admin/knowledge-events?page=0", headers=admin)).status_code == 422
    finally:
        await engine.dispose()
