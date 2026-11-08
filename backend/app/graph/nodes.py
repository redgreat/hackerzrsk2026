"""陪练图节点。

先评估、后回复：客户态度由 evaluate_turn 更新后的信任值决定，客户 Agent 不能自行“被说服”。
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.graph import rules
from app.graph.schemas import CoachOutput, TurnEvaluation
from app.graph.state import PracticeContext, PracticeState
from app.prompts.coach import coach_messages_text
from app.prompts.customer import customer_system
from app.prompts.evaluator import evaluator_messages_text
from app.prompts.hint import hint_messages_text
from app.services.memory import describe_profile, load_profile, save_practice_result


def _seq(state: PracticeState) -> int:
    return len(state.get("transcript", []))


async def init_scenario(state: PracticeState, runtime: Runtime[PracticeContext]) -> dict:
    scenario = runtime.context.scenarios.get(state["scenario_id"])
    r = scenario.state_rules
    update: dict = {
        "trust": r.initial_trust,
        "trust_curve": [r.initial_trust],
        "open_objections": [o.id for o in scenario.persona.objections],
        "resolved_objections": [],
        "turn": 0,
        "hints_used": 0,
        "inner_thoughts": [],
        "status": "ongoing",
        "pending": None,
        "last_hint": None,
        "report": None,
    }
    if scenario.opening.speaker == "customer" and scenario.opening.line:
        line = scenario.opening.line
        update["messages"] = [AIMessage(content=line)]
        update["transcript"] = [{"seq": 0, "role": "customer", "turn": 0, "content": line}]
    return update


async def wait_input(state: PracticeState) -> dict:
    """中断等待员工操作：{"type": "message", "text": ...} / {"type": "hint"} / {"type": "end"}。"""
    payload = interrupt({"await": "input", "turn": state.get("turn", 0)})
    return {"pending": payload}


def route_input(state: PracticeState) -> str:
    match (state.get("pending") or {}).get("type"):
        case "message":
            return "evaluate_turn"
        case "hint":
            return "hint"
        case _:
            return "coach_report"


async def evaluate_turn(state: PracticeState, runtime: Runtime[PracticeContext]) -> dict:
    ctx = runtime.context
    scenario = ctx.scenarios.get(state["scenario_id"])
    said = state["pending"]["text"].strip()
    turn = state["turn"] + 1
    system, user = evaluator_messages_text(
        scenario, state["trust"], state["open_objections"], state.get("transcript", []), said
    )
    ev = await ctx.llm.structured(
        "evaluator", [SystemMessage(content=system), HumanMessage(content=user)], TurnEvaluation
    )
    o = rules.apply_evaluation(scenario, state["trust"], state["open_objections"], turn, ev)
    thought = {
        "turn": turn,
        "trust_before": o.trust_before,
        "trust_after": o.trust_after,
        "delta": o.delta,
        "thought": ev.inner_thought,
        "behaviors": ev.behaviors,
        "resolved": o.resolved,
    }
    return {
        "turn": turn,
        "trust": o.trust_after,
        "trust_curve": [*state["trust_curve"], o.trust_after],
        "open_objections": o.open_objections,
        "resolved_objections": [*state["resolved_objections"], *o.resolved],
        "status": o.status,
        "inner_thoughts": [*state["inner_thoughts"], thought],
        "messages": [HumanMessage(content=said)],
        "transcript": [
            {
                "seq": _seq(state),
                "role": "user",
                "turn": turn,
                "content": said,
                "trust_delta": o.delta,
                "trust_after": o.trust_after,
                "inner_thought": ev.inner_thought,
                "meta": {"behaviors": ev.behaviors, "resolved": o.resolved},
            }
        ],
        "pending": None,
    }


async def customer_reply(state: PracticeState, runtime: Runtime[PracticeContext]) -> dict:
    ctx = runtime.context
    scenario = ctx.scenarios.get(state["scenario_id"])
    system = customer_system(
        scenario, state["trust"], state["open_objections"], state["resolved_objections"], state["status"]
    )
    text = ""
    async for piece in ctx.llm.stream_text("customer", [SystemMessage(content=system), *state["messages"]]):
        text += piece
        runtime.stream_writer({"type": "token", "text": piece})
    text = text.strip() or {"deal": scenario.deal_line, "hangup": scenario.hangup_line}.get(
        state["status"], "嗯，你继续说。"
    )
    return {
        "messages": [AIMessage(content=text)],
        "transcript": [{"seq": _seq(state), "role": "customer", "turn": state["turn"], "content": text}],
    }


def check_end(state: PracticeState) -> str:
    return "wait_input" if state["status"] == "ongoing" else "coach_report"


async def _references(ctx: PracticeContext, query: str, scenario_id: str, k: int = 3) -> list:
    return await ctx.knowledge.search(query, scenario_id, k) if ctx.knowledge else []


async def hint(state: PracticeState, runtime: Runtime[PracticeContext]) -> dict:
    ctx = runtime.context
    scenario = ctx.scenarios.get(state["scenario_id"])
    last_customer = next(
        (t["content"] for t in reversed(state.get("transcript", [])) if t["role"] == "customer"), ""
    )
    open_texts = " ".join(o.text for oid in state["open_objections"] if (o := scenario.objection(oid)))
    refs = await _references(ctx, f"{last_customer} {open_texts}", scenario.id, 2)
    profile = describe_profile(await load_profile(runtime.store, state["user_id"]))
    system, user = hint_messages_text(
        scenario, state["open_objections"], state.get("transcript", []), refs, profile
    )
    text = (await ctx.llm.text("hint", [SystemMessage(content=system), HumanMessage(content=user)])).strip()
    runtime.stream_writer({"type": "hint", "text": text})
    return {
        "hints_used": state["hints_used"] + 1,
        "last_hint": text,
        "transcript": [{"seq": _seq(state), "role": "hint", "turn": state["turn"], "content": text}],
        "pending": None,
    }


async def coach_report(state: PracticeState, runtime: Runtime[PracticeContext]) -> dict:
    ctx = runtime.context
    scenario = ctx.scenarios.get(state["scenario_id"])
    rubric = ctx.scenarios.rubric_for(scenario)
    status = "user_end" if state["status"] == "ongoing" else state["status"]
    runtime.stream_writer({"type": "status", "status": status})
    base = {
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "rubric": rubric.name,
        "outcome": status,
        "turns": state["turn"],
        "hints_used": state["hints_used"],
        "trust_curve": state["trust_curve"],
        "inner_thoughts": state["inner_thoughts"],
    }
    if state["turn"] == 0:
        report = {
            **base,
            "total_score": 0,
            "summary": "本次没有进行有效对话，再来一次吧！",
            "dimension_scores": [
                {"name": d.name, "score": 1, "comment": "未进行对话"} for d in rubric.dimensions
            ],
            "highlights": ["愿意开始尝试就是第一步"],
            "improvements": ["大胆开口，先从礼貌开场和一个开放式问题开始"],
            "turn_reviews": [],
            "references": [],
        }
    else:
        user_lines = " ".join(t["content"] for t in state.get("transcript", []) if t["role"] == "user")
        refs = await _references(ctx, f"{scenario.goal} {user_lines[-300:]}", scenario.id, 3)
        profile = describe_profile(await load_profile(runtime.store, state["user_id"]))
        system, user = coach_messages_text(scenario, rubric, {**state, "status": status}, refs, profile)
        out = await ctx.llm.structured(
            "coach", [SystemMessage(content=system), HumanMessage(content=user)], CoachOutput
        )
        dims = rules.normalize_dimensions(rubric, out)
        report = {
            **base,
            "total_score": rules.total_score(rubric, dims, state["hints_used"]),
            "summary": out.summary,
            "dimension_scores": [d.model_dump() for d in dims],
            "highlights": out.highlights or ["坚持完成了整场对练"],
            "improvements": out.improvements,
            "turn_reviews": [r.model_dump() for r in out.turn_reviews],
            "references": [s.title for s in refs],
        }
        await save_practice_result(runtime.store, state["user_id"], scenario.id, report)
    runtime.stream_writer({"type": "report_ready", "total_score": report["total_score"]})
    return {"status": status, "report": report, "pending": None}
