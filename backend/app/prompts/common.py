from app.services.scenarios import Scenario


def transcript_text(transcript: list[dict], persona_name: str) -> str:
    lines = []
    for t in transcript:
        if t["role"] == "user":
            lines.append(f"第{t['turn']}轮 员工：{t['content']}")
        elif t["role"] == "customer":
            lines.append(f"{persona_name}（客户）：{t['content']}")
    return "\n".join(lines) or "（尚无对话）"


def objections_text(scenario: Scenario, ids: list[str], with_hints: bool = False) -> str:
    lines = []
    for oid in ids:
        o = scenario.objection(oid)
        if not o:
            continue
        line = f"- [{o.id}] {o.text}{'（关键）' if o.key else ''}"
        if with_hints and o.resolve_hints:
            line += f" 化解要点：{'、'.join(o.resolve_hints)}"
        lines.append(line)
    return "\n".join(lines) or "（无）"


def snippets_text(snippets: list) -> str:
    return "\n\n".join(f"《{s.title}》\n{s.content}" for s in snippets) or "（无）"
