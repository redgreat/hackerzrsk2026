"""从显式准备的去标识输入生成培训候选；不修改原文，不启用检索。"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import AppError, Conflict, NotFound
from app.db.models import KnowledgeEvent, ModelUsage, TrainingCleanup, TranscriptSnapshot
from app.prompts.cleanup import SYSTEM, VERSION
from app.services.llm.usage import usage_scope
from app.services.transcripts import Labels, masked


class InputLine(BaseModel):
    seq: int = Field(ge=1)
    speaker: Literal["agent", "customer", "unknown"]
    text: str = Field(min_length=1, max_length=2000)


class CleanupInput(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    event_id: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    deidentified: Literal[True]
    lines: list[InputLine] = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def unique_lines(self):
        seqs = [line.seq for line in self.lines]
        if seqs != sorted(set(seqs)):
            raise ValueError("输入片段编号必须唯一且按顺序排列")
        return self


class TrainingLine(BaseModel):
    speaker: Literal["agent", "customer"]
    text: str = Field(min_length=1, max_length=2000)
    source_seqs: list[int]
    added: bool


class Issue(BaseModel):
    severity: Literal["minor", "major"]
    category: Literal["logic", "role", "policy", "privacy", "transcription"]
    description: str


class CleanupOutput(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1)
    labels: Labels
    dialogue: list[TrainingLine] = Field(min_length=2, max_length=100)
    changes: list[str]
    issues: list[Issue]
    learning_points: list[str]


def classify(output: CleanupOutput, inputs: CleanupInput) -> tuple[str, list[str]]:
    seqs = {line.seq for line in inputs.lines}
    roles = {line.seq: line.speaker for line in inputs.lines}
    problems = []
    for line in output.dialogue:
        if any(seq not in seqs for seq in line.source_seqs):
            problems.append("模型引用了输入中不存在的片段")
        if line.added == bool(line.source_seqs):
            problems.append("新增教学内容与原文证据标记不一致")
        if any(roles.get(seq) not in {line.speaker, "unknown"} for seq in line.source_seqs):
            problems.append("培训对话的角色与原片段引用不一致")
    if any(line.speaker == "unknown" for line in inputs.lines):
        problems.append("输入存在无法确认的角色")
    if any(i.severity == "major" for i in output.issues):
        problems.append("模型识别到重大问题")
    return ("review_required" if problems else "candidate"), list(dict.fromkeys(problems))


async def cleanup(sf, llm, inputs: CleanupInput) -> dict:
    if llm.cfg.provider != "openai":
        raise AppError("智能清洗需要真实模型，请设置 LLM__PROVIDER=openai")
    async with sf() as db:
        event = await db.get(KnowledgeEvent, inputs.event_id)
        if event is None:
            raise NotFound("知识事件不存在")
        if event.review_revision != inputs.expected_revision:
            raise Conflict("事件已修改，请重新准备清洗输入")
        snapshot = await db.get(TranscriptSnapshot, event.snapshot_id)
        allowed = {
            s["seq"] for s in snapshot.segments if event.segment_start <= s["seq"] <= event.segment_end
        }
        if {line.seq for line in inputs.lines} != allowed:
            raise AppError("输入必须覆盖本事件完整上下文，不能静默截断")
    # 只向模型发送显式准备的去标识文本，不发送源记录标识、地址、原始文件或审核意见。
    prepared = masked([line.model_dump() for line in inputs.lines])
    payload = json.dumps(prepared, ensure_ascii=False)
    if len(payload) > 30000:
        raise AppError("输入过长，请先拆分事件")
    with usage_scope() as usage:
        output = await llm.structured(
            "cleanup", [SystemMessage(content=SYSTEM), HumanMessage(content=payload)], CleanupOutput
        )
    status, checks = classify(output, inputs)
    result = masked(output.model_dump())
    result["checks"] = checks
    async with sf() as db, db.begin():
        event = await db.get(KnowledgeEvent, inputs.event_id, with_for_update=True)
        if event.review_revision != inputs.expected_revision:
            raise Conflict("清洗期间事件已修改，请重新处理")
        run = TrainingCleanup(
            event_id=event.id,
            input_hash=hashlib.sha256(payload.encode()).hexdigest(),
            prepared_input={"lines": prepared, "event_revision": inputs.expected_revision},
            result=result,
            status=status,
            model=llm.model_name("cleanup"),
            prompt_version=VERSION,
            cost_yuan=usage.cost_yuan
            if llm.model_name("cleanup") in getattr(llm.cfg, "pricing", {})
            else None,
        )
        db.add(run)
        for r in usage.records:
            db.add(
                ModelUsage(
                    purpose=r.purpose,
                    model=r.model,
                    prompt_tokens=r.prompt_tokens,
                    completion_tokens=r.completion_tokens,
                    cost_yuan=r.cost_yuan,
                    latency_ms=r.latency_ms,
                )
            )
        await db.flush()
        return {"id": run.id, "status": status, "result": result}


async def cleanup_file(sf, llm, path: Path) -> dict:
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return await cleanup(sf, llm, CleanupInput.model_validate_json(text))
