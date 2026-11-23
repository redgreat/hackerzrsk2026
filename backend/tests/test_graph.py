import uuid

import pytest
from langgraph.types import Command

from app.core.errors import UpstreamError
from app.services.llm import usage_scope
from app.services.memory import load_profile


def _cfg():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


async def _run(graph, ctx, payload, cfg):
    events = []
    async for mode, chunk in graph.astream(payload, cfg, context=ctx, stream_mode=["custom", "updates"]):
        if mode == "custom":
            events.append(chunk)
    return events


async def test_customer_opening_and_wait(graph, ctx):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S01"}, cfg)
    snap = await graph.aget_state(cfg)
    assert snap.next == ("wait_input",)
    assert snap.values["transcript"][0]["role"] == "customer"
    assert snap.values["trust"] == 20


async def test_message_hint_end_flow(graph, ctx, store):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S01"}, cfg)

    with usage_scope() as usage:
        events = await _run(
            graph,
            ctx,
            Command(
                resume={
                    "type": "message",
                    "text": "赵女士，非常抱歉让您久等了。方便先说说昨天故障的具体时间和您现在最着急的问题吗？",
                }
            ),
            cfg,
        )
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert tokens
    assert {r.purpose for r in usage.records} == {"evaluator", "customer"}
    assert usage.prompt_tokens > 0

    snap = await graph.aget_state(cfg)
    v = snap.values
    assert v["turn"] == 1 and v["trust"] > 20
    assert [t["role"] for t in v["transcript"]] == ["customer", "user", "customer"]
    assert v["transcript"][1]["inner_thought"]

    events = await _run(graph, ctx, Command(resume={"type": "hint"}), cfg)
    assert any(e["type"] == "hint" for e in events)
    v = (await graph.aget_state(cfg)).values
    assert v["hints_used"] == 1 and v["turn"] == 1

    events = await _run(graph, ctx, Command(resume={"type": "end"}), cfg)
    assert any(e["type"] == "report_ready" for e in events)
    snap = await graph.aget_state(cfg)
    report = snap.values["report"]
    assert snap.next == ()
    assert report["outcome"] == "user_end"
    assert len(report["dimension_scores"]) == 5
    assert 0 < report["total_score"] <= 100
    assert report["highlights"]
    assert (await load_profile(store, "u1"))["practice_count"] == 1


async def test_user_opens_scenario(graph, ctx):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S02"}, cfg)
    v = (await graph.aget_state(cfg)).values
    assert v["transcript"][0]["role"] == "customer"


async def test_failed_report_can_resume_from_checkpoint(graph, ctx, monkeypatch):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S01"}, cfg)
    await _run(graph, ctx, Command(resume={"type": "message", "text": "您好，方便说下故障吗？"}), cfg)
    calls = 0
    structured = ctx.llm.structured

    async def score(purpose, messages, schema):
        nonlocal calls
        assert purpose == "coach"
        calls += 1
        if calls == 1:
            raise TimeoutError
        return await structured(purpose, messages, schema)

    monkeypatch.setattr(ctx.llm, "structured", score)
    with pytest.raises(UpstreamError, match="评分等待超时"):
        await _run(graph, ctx, Command(resume={"type": "end"}), cfg)
    assert calls == 1
    assert (await graph.aget_state(cfg)).next == ("coach_report",)
    await _run(graph, ctx, None, cfg)
    assert (await graph.aget_state(cfg)).values["report"]["outcome"] == "user_end"


async def test_off_topic_skips_models_and_does_not_count(graph, ctx):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S01"}, cfg)
    with usage_scope() as usage:
        for said in ("你是谁,你今天开心吗", "???"):
            events = await _run(graph, ctx, Command(resume={"type": "message", "text": said}), cfg)
            assert "这个先不聊" in next(e["text"] for e in events if e["type"] == "token")
    assert not usage.records
    values = (await graph.aget_state(cfg)).values
    assert values["turn"] == 0 and values["trust"] == 20
    assert len(values["messages"]) == 1


async def test_evaluator_rejects_unrelated_chitchat(graph, ctx, monkeypatch):
    async def evaluate(purpose, messages, schema):
        assert purpose == "evaluator"
        return schema(is_relevant=False, trust_delta=0, inner_thought="")

    monkeypatch.setattr(ctx.llm, "structured", evaluate)
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "C07"}, cfg)
    with usage_scope() as usage:
        events = await _run(graph, ctx, Command(resume={"type": "message", "text": "你好，今天天气"}), cfg)
    assert [e["text"] for e in events if e["type"] == "token"] == [
        "这个先不聊。你打这通电话是想跟我确认什么？"
    ]
    assert not usage.records
    assert (await graph.aget_state(cfg)).values["turn"] == 0


async def test_out_of_character_reply_is_never_emitted(graph, ctx, monkeypatch):
    async def customer_stream(purpose, messages):
        yield "我是"
        yield "千问呀。"

    monkeypatch.setattr(ctx.llm, "stream_text", customer_stream)
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S01"}, cfg)
    events = await _run(
        graph, ctx, Command(resume={"type": "message", "text": "您好，方便说下故障吗？"}), cfg
    )
    replies = [e["text"] for e in events if e["type"] == "token"]
    assert len(replies) == 1 and replies[0].startswith("咱们还是说正事吧")
    values = (await graph.aget_state(cfg)).values
    assert values["transcript"][-1]["content"] == replies[0]


async def test_reaching_deal_ends_with_report(graph, ctx):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u2", "scenario_id": "S01"}, cfg)
    lines = [
        "真的非常抱歉，理解您着急，给您添麻烦了，能说说昨天具体什么情况吗？",
        "我今天安排专人跟进，下午五点前给您回电话说明方案，您看可以吗？",
        "关于补偿我会如实上报申请，明天中午前反馈结果给您，您还有什么需要我确认的吗？",
        "非常理解您，这次我本人跟进到底，五点前专人联系您，您看还有哪些地方需要我帮忙？",
        "抱歉让您久等，我已经升级处理，今天专人跟进，还有其他问题吗？",
        "理解您的心情，我们五点前给出方案，您看这样安排是否方便？",
    ]
    for line in lines:
        snap = await graph.aget_state(cfg)
        if not snap.next:
            break
        await _run(graph, ctx, Command(resume={"type": "message", "text": line}), cfg)
    v = (await graph.aget_state(cfg)).values
    assert v["status"] == "deal"
    assert v["report"]["outcome"] == "deal"
    assert v["turn"] >= 4  # min_turns_to_deal
