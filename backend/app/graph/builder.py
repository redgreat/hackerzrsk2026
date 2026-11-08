"""陪练图定义。

START → init_scenario → wait_input(interrupt)
  wait_input ─message→ evaluate_turn → customer_reply ─check_end─┬─ongoing→ wait_input
             ─hint───→ hint → wait_input                         └─结束──→ coach_report → END
             ─end────→ coach_report → END
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import RetryPolicy

from app.core.errors import UpstreamError
from app.graph import nodes
from app.graph.state import PracticeContext, PracticeState

LLM_RETRY = RetryPolicy(max_attempts=2, retry_on=UpstreamError)


def build_practice_graph(
    checkpointer: BaseCheckpointSaver, store: BaseStore | None = None
) -> CompiledStateGraph:
    g = StateGraph(PracticeState, context_schema=PracticeContext)
    g.add_node("init_scenario", nodes.init_scenario)
    g.add_node("wait_input", nodes.wait_input)
    g.add_node("evaluate_turn", nodes.evaluate_turn, retry_policy=LLM_RETRY)
    g.add_node("customer_reply", nodes.customer_reply)
    g.add_node("hint", nodes.hint, retry_policy=LLM_RETRY)
    g.add_node("coach_report", nodes.coach_report, retry_policy=LLM_RETRY)

    g.add_edge(START, "init_scenario")
    g.add_edge("init_scenario", "wait_input")
    g.add_conditional_edges("wait_input", nodes.route_input, ["evaluate_turn", "hint", "coach_report"])
    g.add_edge("evaluate_turn", "customer_reply")
    g.add_conditional_edges("customer_reply", nodes.check_end, ["wait_input", "coach_report"])
    g.add_edge("hint", "wait_input")
    g.add_edge("coach_report", END)
    return g.compile(checkpointer=checkpointer, store=store, name="practice")
