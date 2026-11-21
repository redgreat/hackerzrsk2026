from app.services.recording_rules import transcript_prompt_text
from app.services.scenarios import Rubric, Scenario

CUSTOMER_TYPES = [
    "忘记还款",
    "资金困难",
    "拖延推脱",
    "情绪激动",
    "质疑金额",
    "第三方接听",
    "恶意拖欠",
    "其他",
]

ANALYST_SYSTEM = """你是贷后催收呼叫中心的资深质检兼培训师。下面是一通被评为“优秀录音”的通话转写（已脱敏），
请把它整理成给新人学习的教材。

## 评分维度（每个维度打 1~5 分整数，name 必须与下列完全一致）
{dimensions}

## 合规红线（如出现必须写入 compliance_issues）
{red_lines}

## 可关联的对练场景（related_scenario_ids 只能从这里选，选 0~2 个最相近的）
{scenarios}

## 输出要求
1. customer_type 只能从以下选择：{customer_types}。
2. highlights 选 3~6 句最值得新人学习的**坐席**原话，index 用转写中的 [序号]。
3. stages 按时间顺序标出通话阶段的起始 [序号]。
4. learning_points 3~5 条，具体可模仿，例如“先核实本人再说欠款”。
5. questions 出 2~3 道听录音答题：围绕“坐席为什么这样说/下一步该怎么说/哪句话合规”，
   题干不要出现转写原文的序号，选项 3~4 个且只有一个最佳（判断题 options 固定为 ["正确", "错误"]）。
6. 所有输出不得出现客户姓名、手机号、身份证号、车牌、具体住址；可以用“客户”“坐席”指代。
7. 转写可能有识别错误，按上下文理解，不要据此扣分。"""


def analyst_messages_text(
    transcript: list[dict], rubric: Rubric, scenarios: list[Scenario]
) -> tuple[str, str]:
    dims = "\n".join(f"- {d.name}：5 分={d.good}；1 分={d.bad}" for d in rubric.dimensions)
    system = ANALYST_SYSTEM.format(
        dimensions=dims,
        red_lines="\n".join(f"- {r}" for r in rubric.red_lines) or "（无）",
        scenarios="\n".join(f"- {s.id}：{s.name}" for s in scenarios) or "（无）",
        customer_types="、".join(CUSTOMER_TYPES),
    )
    return system, f"【录音转写】\n{transcript_prompt_text(transcript)}"
