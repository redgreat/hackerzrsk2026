"""离线 Stub 模型：无需密钥即可跑通全流程（开发、测试、演示彩排）。

按提示词中的约定标记做简单规则推断，输出格式与真实模型一致。
"""

import json
import re
from collections.abc import Iterator
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

GOOD_QUESTION = re.compile(r"[?？]|哪些|怎么|什么|如何|是否|能不能|方便.*说")
EMPATHY = re.compile(r"理解|明白|抱歉|不好意思|确实|您说得对|辛苦")
PUSHY = re.compile(r"最低价|马上签|今天必须|打折|便宜点|别家.*(差|垃圾)")
VIOLATION = re.compile(r"保证|绝对|百分百|100%|肯定没问题")
# 催收红线（威胁恐吓、辱骂、冒充公检法、向第三方施压等）
RED_LINE = re.compile(
    r"坐牢|抓你|弄死|找人上门|曝光你|告诉你(家人|单位|领导|同事)|公安局|派出所|法院的人|骗子|老赖|滚"
)


def _text(msg: BaseMessage) -> str:
    return msg.content if isinstance(msg.content, str) else str(msg.content)


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 1.5))


def _stub_customer(system: str) -> str:
    if "【本轮结局：成交】" in system:
        return "嗯，你说的这些我基本认可。行，那你安排一下，下周我们约个时间详细聊方案。"
    if "【本轮结局：挂断】" in system:
        return "算了算了，我没时间听这些，先这样吧。"
    m = re.search(r"当前信任值：(\d+)", system)
    trust = int(m.group(1)) if m else 30
    if trust < 25:
        return "你们这个价格确实比别家高不少，说重点，凭什么贵？"
    if trust < 45:
        return "嗯……你说的有点道理，但我还是担心上线以后的问题，你们怎么保证？"
    if trust < 65:
        return "这个思路可以。那售后响应一般多久？出了问题谁来负责？"
    return "听起来还不错，付款方式上有没有灵活一点的方案？"


def _stub_evaluator(system: str, user: str) -> dict:
    m = re.search(r"员工本轮发言：(.+)", user, re.S)
    said = m.group(1).strip() if m else user
    delta, behaviors = 0, []
    if GOOD_QUESTION.search(said):
        delta += 6
        behaviors.append("有效提问")
    if EMPATHY.search(said):
        delta += 4
        behaviors.append("共情认同")
    if PUSHY.search(said):
        delta -= 10
        behaviors.append("急于压单/降价")
    if VIOLATION.search(said):
        delta -= 15
        behaviors.append("违规承诺")
    if len(said) < 6:
        delta -= 3
        behaviors.append("回答过于简短")
    red_line = None
    red_lines = (
        re.findall(r"^- (.+)$", system.split("## 合规红线", 1)[1].split("\n\n", 1)[0], re.M)
        if "## 合规红线" in system
        else []
    )
    if red_lines and RED_LINE.search(said):
        red_line = red_lines[0]
        delta -= 20
        behaviors.append("触犯红线")
    resolved = []
    for oid, hints in re.findall(r"- \[(\w+)\][^\n]*?化解要点：([^\n]*)", system):
        keywords = [k.strip() for k in re.split(r"[，,、;；]", hints) if k.strip()]
        if len(said) >= 15 and any(k and k in said for k in keywords):
            resolved.append(oid)
            delta += 10
    thought = "他好像真的在关心我的问题。" if delta > 0 else "又是套话，没说到点子上。"
    return {
        "trust_delta": delta,
        "resolved_objection_ids": resolved,
        "behaviors": behaviors or ["表达一般"],
        "inner_thought": thought,
        "hangup": False,
        "red_line": red_line,
        "reason": "Stub 规则评估",
    }


def _stub_coach(system: str, user: str) -> dict:
    dims = re.findall(r"^- (.+?)（权重", system, re.M)
    turns = re.findall(r"第(\d+)轮 员工：(.+)", user)
    reviews = [
        {
            "turn": int(t),
            "user_said": s.strip()[:80],
            "issue": "可以先确认客户关注点，再给出针对性回应。",
            "better_reply": "我理解您对价格的顾虑，方便说说您最看重的是哪几个方面吗？我针对性地给您算笔账。",
        }
        for t, s in turns[:2]
    ]
    return {
        "summary": "整体表现稳定，提问意识不错，价值塑造还可以更贴近客户需求。",
        "dimension_scores": [
            {"name": d, "score": 4 if i % 2 == 0 else 3, "comment": f"{d}表现中规中矩。"}
            for i, d in enumerate(dims)
        ],
        "highlights": ["能主动向客户提问，了解对方关注点"],
        "improvements": ["回应异议时先认同再澄清，避免直接反驳", "结尾明确提出下一步行动"],
        "turn_reviews": reviews,
    }


def _stub_analyst(system: str, user: str) -> dict:
    dims = re.findall(r"^- (.+?)：5 分=", system, re.M)
    lines = re.findall(r"^\[(\d+)\] (坐席|客户)：(.+)$", user, re.M)
    agent = [int(i) for i, who, _ in lines if who == "坐席"]
    scenario_ids = re.findall(r"^- (C\d+)：", system, re.M)
    return {
        "title": "首逾提醒并锁定当日还款",
        "summary": "坐席核实身份后提醒逾期，了解是换卡忘转，告知征信影响并锁定当天下午还款。",
        "customer_type": "忘记还款",
        "outcome": "承诺还款",
        "tags": ["身份核实", "征信告知", "锁定承诺"],
        "stages": [
            {"name": "开场核实", "start_index": 0},
            {"name": "确认收尾", "start_index": max(len(lines) - 2, 0)},
        ],
        "highlights": [
            {"index": i, "technique": t, "why": "表达具体、语气友好，值得模仿。"}
            for i, t in zip(agent[:3], ["自报家门", "共情接话", "锁定承诺"], strict=False)
        ],
        "dimension_scores": [
            {"name": d, "score": 5 if i % 2 == 0 else 4, "comment": "表现到位。"} for i, d in enumerate(dims)
        ],
        "compliance_issues": [],
        "learning_points": ["先核实本人再谈欠款", "用客户的良好记录做正向激励", "收尾复述金额、时间与方式"],
        "related_scenario_ids": scenario_ids[:1],
        "questions": [
            {
                "type": "single",
                "stem": "坐席在说明来电目的前，首先做了什么？",
                "options": ["直接报欠款金额", "核实是否客户本人", "告知将上门催收", "询问客户收入"],
                "answer": [1],
                "explanation": "先核实本人身份，避免向第三方泄露债务信息。",
            },
            {
                "type": "judge",
                "stem": "坐席在收尾时复述了还款时间与方式，这样做有助于客户兑现承诺。",
                "options": ["正确", "错误"],
                "answer": [0],
                "explanation": "复述承诺能让客户确认并加深印象，提高兑现率。",
            },
        ],
    }


def _stub_hint() -> str:
    return "先认同客户的顾虑，再用开放式问题挖掘他最在意的点，例如：“您最担心的是哪方面？”"


class StubChatModel(BaseChatModel):
    purpose: str = "customer"

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _respond(self, messages: list[BaseMessage]) -> str:
        system = "\n".join(_text(m) for m in messages if m.type == "system")
        user = "\n".join(_text(m) for m in messages if m.type == "human")
        match self.purpose:
            case "evaluator":
                return json.dumps(_stub_evaluator(system, user), ensure_ascii=False)
            case "coach":
                return json.dumps(_stub_coach(system, user), ensure_ascii=False)
            case "hint":
                return _stub_hint()
            case "analyst":
                return json.dumps(_stub_analyst(system, user), ensure_ascii=False)
            case _:
                return _stub_customer(system)

    def _usage(self, messages: list[BaseMessage], output: str) -> dict:
        pt = sum(_estimate_tokens(_text(m)) for m in messages)
        ct = _estimate_tokens(output)
        return {"input_tokens": pt, "output_tokens": ct, "total_tokens": pt + ct}

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any
    ) -> ChatResult:
        out = self._respond(messages)
        msg = AIMessage(
            content=out, usage_metadata=self._usage(messages, out), response_metadata={"model_name": "stub"}
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any
    ) -> Iterator[ChatGenerationChunk]:
        out = self._respond(messages)
        for i in range(0, len(out), 4):
            yield ChatGenerationChunk(message=AIMessageChunk(content=out[i : i + 4]))
        yield ChatGenerationChunk(
            message=AIMessageChunk(content="", usage_metadata=self._usage(messages, out))
        )
