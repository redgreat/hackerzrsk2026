import uuid

from langgraph.types import Command

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
    assert snap.values["trust"] == 30


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
                    "text": "王经理您好，理解您关注价格，方便说说您主要在对比哪些方面吗？",
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
    assert v["turn"] == 1 and v["trust"] > 30
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
    assert len(report["dimension_scores"]) == 6
    assert 0 < report["total_score"] <= 100
    assert report["highlights"]
    assert (await load_profile(store, "u1"))["practice_count"] == 1


async def test_user_opens_scenario(graph, ctx):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S02"}, cfg)
    v = (await graph.aget_state(cfg)).values
    assert v.get("transcript", []) == []


async def test_reaching_deal_ends_with_report(graph, ctx):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u2", "scenario_id": "S03"}, cfg)
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
