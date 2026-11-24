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
PUSHY = re.compile(r"马上|今天必须|你自己|不归我管|别再问|爱用不用")
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
    if "【本轮结局：目标达成】" in system:
        return "好，那就按你说的时间处理，到时请你主动联系我。"
    if "【本轮结局：挂断】" in system:
        return "算了算了，我没时间听这些，先这样吧。"
    m = re.search(r"当前信任值：(\d+)", system)
    trust = int(m.group(1)) if m else 30
    if trust < 25:
        return "我已经等很久了，你们到底有没有人在认真处理？"
    if trust < 45:
        return "我不想再听‘尽快’，你能不能把现在的进度说清楚？"
    if trust < 65:
        return "这样说清楚多了。那下一次具体什么时候给我反馈？"
    return "可以，那你再帮我确认一下接下来由谁跟进、我需要做什么。"


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
        behaviors.append("催促或推诿")
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
        "is_relevant": True,
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
            "better_reply": "我理解您现在很着急。我先把您的诉求和当前进度确认清楚，再给您一个可以兑现的下一次反馈时间。",
        }
        for t, s in turns[:2]
    ]
    return {
        "summary": "整体表现稳定，能主动确认问题，方案和回访节点还可以更具体。",
        "dimension_scores": [
            {"name": d, "score": 4 if i % 2 == 0 else 3, "comment": f"{d}表现中规中矩。"}
            for i, d in enumerate(dims)
        ],
        "highlights": ["能主动向客户提问，确认对方真正诉求"],
        "improvements": ["先共情再澄清，避免机械套话", "结尾确认负责人、动作和时间"],
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
    return "先接住客户情绪，再用一个具体问题澄清诉求，例如：“我理解您很着急，您现在最需要我先确认进度，还是先给出临时处理办法？”"


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
                if '"title": "GeneratedExamQuestions"' in system:
                    return json.dumps(
                        {
                            "questions": [
                                {
                                    "topic": "核实身份后再沟通",
                                    "stem": "通话中，对方尚未确认本人身份，工作人员应该怎么做？",
                                    "options": ["先核实身份", "直接透露欠款", "询问对方同事", "承诺减免本金"],
                                    "correct_index": 0,
                                    "explanation": "先核实身份，再沟通具体业务，避免泄露客户信息。",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                if '"title": "PracticeEvidence"' in system:
                    return json.dumps(
                        {"seqs": [int(value) for value in re.findall(r"(?m)^(\d+) ", user)[:6]]}
                    )
                if '"title": "GeneratedPractices"' in system:
                    return json.dumps(
                        {
                            "scenarios": [
                                {
                                    "id": "draft",
                                    "name": "核对当前还款困难",
                                    "background": "你负责跟进还款，客户提出当前有困难。",
                                    "goal": "问清客户困难并确认下一步。",
                                    "persona": {
                                        "name": "周先生",
                                        "role": "客户",
                                        "personality": "愿意沟通",
                                        "speaking_style": "简短直接",
                                    },
                                    "scoring": "collection_default",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
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
