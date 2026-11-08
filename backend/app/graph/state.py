"""陪练图状态契约。"""

import operator
from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.services.knowledge import KnowledgeBase
from app.services.llm import LLMGateway
from app.services.scenarios import ScenarioRegistry

Status = Literal["ongoing", "deal", "hangup", "max_turns", "user_end"]


class PracticeState(TypedDict, total=False):
    session_id: str
    user_id: str
    scenario_id: str
    # 客户 Agent 的对话上下文：员工=Human，客户=AI
    messages: Annotated[list[AnyMessage], add_messages]
    # 面向展示/落库的逐条记录（含求助），只追加；seq 全局递增
    transcript: Annotated[list[dict], operator.add]
    trust: int
    trust_curve: list[int]
    open_objections: list[str]
    resolved_objections: list[str]
    turn: int
    hints_used: int
    inner_thoughts: list[dict]
    status: Status
    pending: dict | None
    last_hint: str | None
    report: dict | None


@dataclass
class PracticeContext:
    """运行时依赖（不进入 checkpoint）。"""

    llm: LLMGateway
    scenarios: ScenarioRegistry
    knowledge: KnowledgeBase | None = None
