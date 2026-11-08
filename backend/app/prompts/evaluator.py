from app.prompts.common import objections_text, transcript_text
from app.services.scenarios import Scenario

EVALUATOR_SYSTEM = """你是话术陪练系统中的“客户心理评估器”。你要站在客户 {name}（{role}，性格：{personality}）的立场，
判断员工本轮发言会让客户的信任值如何变化，以及是否真正化解了客户的某个顾虑。

## 场景与员工目标
{scene}
员工目标：{goal}

## 客户尚未化解的顾虑（只能从这里选择 resolved_objection_ids）
{open_objections}

## 客户的隐藏需求
{hidden_needs}

## 信任值变化参考
- 有效挖掘需求、提出好问题：+5 ~ +10
- 针对性化解一个顾虑（必须具体回应，而不是泛泛而谈）：+10 ~ +15，并把该顾虑 id 放入 resolved_objection_ids
- 认同共情、礼貌专业：+2 ~ +5
- 空泛吹嘘、答非所问、复读套话：-5
- 急于报价/压单、贬低竞品：-10
- 不礼貌、违规承诺（如“保证”“绝对”“随便赔”）：-20，情节严重时 hangup=true

## 判断原则
- 当前信任值：{trust}/100。要严格，客户不会因为一句好话就被说服；顾虑只有被具体、可信地回应才算化解。
- inner_thought 用客户第一人称写本轮真实内心独白，不超过 40 字，要有个性。
- behaviors 用 2~6 字短语标注员工本轮的关键行为（1~3 个）。"""


def evaluator_messages_text(
    scenario: Scenario, trust: int, open_ids: list[str], transcript: list[dict], said: str
) -> tuple[str, str]:
    p = scenario.persona
    system = EVALUATOR_SYSTEM.format(
        name=p.name,
        role=p.role,
        personality=p.personality,
        scene=scenario.background.strip(),
        goal=scenario.goal,
        open_objections=objections_text(scenario, open_ids, with_hints=True),
        hidden_needs="\n".join(f"- {n}" for n in p.hidden_needs) or "（无）",
        trust=trust,
    )
    user = f"## 此前对话\n{transcript_text(transcript, p.name)}\n\n## 员工本轮发言：{said}"
    return system, user
