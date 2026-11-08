from app.prompts.common import snippets_text, transcript_text
from app.services.scenarios import Rubric, Scenario

OUTCOME_TEXT = {
    "deal": "客户同意进入下一步（成功）",
    "hangup": "客户挂断（失败）",
    "max_turns": "达到轮数上限，未达成目标",
    "user_end": "员工主动结束",
    "ongoing": "未结束",
}

COACH_SYSTEM = """你是一位资深的{rubric_name}教练，按公司销冠标准为员工的一次话术陪练打分并点评。

## 评分维度（每个维度打 1~5 分整数）
{dimensions}

## 优秀话术参考（来自公司话术库，可在推荐话术中借鉴）
{references}

## 该员工的历史练习画像
{profile}

## 点评要求
1. 鼓励为主：highlights 至少 1 条，必须具体到员工说过的话。
2. summary 一句话总评，30 字以内，先结论后建议。
3. improvements 2~3 条，具体可执行。
4. turn_reviews 选 2~4 个最值得改进的轮次：user_said 摘录员工原话，issue 指出问题，
   better_reply 给出可直接说出口的口语化推荐话术（不超过 80 字）。
5. 如果员工在某维度没有相关表现，按 1~2 分处理并说明原因。
6. dimension_scores 必须覆盖全部维度，name 与上面的维度名称完全一致。"""


def coach_messages_text(
    scenario: Scenario, rubric: Rubric, state: dict, references: list, profile: str
) -> tuple[str, str]:
    dims = "\n".join(
        f"- {d.name}（权重 {d.weight:g}）：5 分={d.good}；1 分={d.bad}" for d in rubric.dimensions
    )
    system = COACH_SYSTEM.format(
        rubric_name=rubric.name.replace("评分表", ""),
        dimensions=dims,
        references=snippets_text(references),
        profile=profile,
    )
    thoughts = (
        "\n".join(
            f"第{t['turn']}轮：信任值 {t['trust_before']}→{t['trust_after']}，客户内心：{t['thought']}"
            for t in state.get("inner_thoughts", [])
        )
        or "（无）"
    )
    user = f"""## 场景：{scenario.name}
{scenario.background.strip()}
员工目标：{scenario.goal}

## 结果：{OUTCOME_TEXT.get(state.get("status", ""), "")}；共 {state.get("turn", 0)} 轮；使用求助 {state.get("hints_used", 0)} 次

## 客户每轮内心变化
{thoughts}

## 完整对话
{transcript_text(state.get("transcript", []), scenario.persona.name)}"""
    return system, user
