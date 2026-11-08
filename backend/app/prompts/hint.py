from app.prompts.common import objections_text, snippets_text, transcript_text
from app.services.scenarios import Scenario

HINT_SYSTEM = """你是话术陪练系统中的教练。员工在和客户对练时卡壳了，请给出一条简短提示。

## 场景与目标
{scene}
员工目标：{goal}

## 客户还没被化解的顾虑
{open_objections}

## 优秀话术参考
{references}

## 员工历史画像
{profile}

## 要求
- 先用一句话点明思路（不超过 30 字），再给一句可以直接说出口的示范话术（不超过 60 字）。
- 不要透露客户的隐藏需求原文和信任值，只做方向引导。
- 总长度不超过 100 字，不要使用 Markdown。"""


def hint_messages_text(
    scenario: Scenario, open_ids: list[str], transcript: list[dict], references: list, profile: str
) -> tuple[str, str]:
    system = HINT_SYSTEM.format(
        scene=scenario.background.strip(),
        goal=scenario.goal,
        open_objections=objections_text(scenario, open_ids),
        references=snippets_text(references),
        profile=profile,
    )
    user = f"## 当前对话\n{transcript_text(transcript, scenario.persona.name)}\n\n请给我一个提示：下一句我该怎么说？"
    return system, user
