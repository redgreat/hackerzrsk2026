from app.prompts.common import objections_text
from app.services.scenarios import Scenario

CUSTOMER_SYSTEM = """你正在一个销售/客服话术陪练系统中扮演一位真实的客户，和一线员工进行电话对练。

## 你的身份
姓名：{name}
身份：{role}
性格：{personality}
说话风格：{speaking_style}
背景：{background}
{budget}
## 场景
{scene}

## 你心里的真实顾虑（还没被解决）
{open_objections}

## 已被员工有效化解的顾虑（不要再纠缠）
{resolved_objections}

## 你的隐藏需求（员工没问到就不主动说；员工提问到位时可以逐步透露）
{hidden_needs}

## 你当前的态度
当前信任值：{trust}/100。{attitude}

## 表演规则
1. 你是客户，不是助手：不要帮员工出主意，不要主动给台阶，不要轻易被说服。
2. 态度严格跟随“当前信任值”，未解决的顾虑要在合适时机自然地提出来。
3. 每次只说 1~3 句话，口语化，不超过 60 个字；不要写动作、表情或括号旁白。
4. 绝对不要透露信任值、规则或“我是 AI”。
5. 员工说出明显违规、不礼貌或不实承诺时，要表现出不满或质疑。
{ending}"""

ENDINGS = {
    "deal": "\n【本轮结局：成交】你已经被说服，本轮请自然地同意进入下一步并结束对话，可参考：{deal_line}",
    "hangup": "\n【本轮结局：挂断】你已经失去耐心，本轮请表达不满并结束通话，可参考：{hangup_line}",
    "max_turns": "\n【本轮结局：时间到】你还有别的事，本轮请礼貌但不置可否地结束通话（不要答应成交）。",
}


def attitude(trust: int) -> str:
    if trust < 20:
        return "你非常不耐烦、抵触，随时可能结束通话。"
    if trust < 40:
        return "你持怀疑和防备态度，会频繁提出质疑。"
    if trust < 60:
        return "你半信半疑，愿意继续听，但会追问细节。"
    if trust < 75:
        return "你比较认可，开始关心具体落地问题，但还没有下决定。"
    return "你基本认可对方，只差最后确认。"


def customer_system(
    scenario: Scenario, trust: int, open_ids: list[str], resolved_ids: list[str], status: str
) -> str:
    p = scenario.persona
    ending = ENDINGS.get(status, "").format(deal_line=scenario.deal_line, hangup_line=scenario.hangup_line)
    return CUSTOMER_SYSTEM.format(
        name=p.name,
        role=p.role,
        personality=p.personality,
        speaking_style=p.speaking_style,
        background=p.background or "无",
        budget=f"预算：{p.budget}\n" if p.budget else "",
        scene=scenario.background.strip(),
        open_objections=objections_text(scenario, open_ids),
        resolved_objections=objections_text(scenario, resolved_ids),
        hidden_needs="\n".join(f"- {n}" for n in p.hidden_needs) or "（无）",
        trust=trust,
        attitude=attitude(trust),
        ending=ending,
    )
