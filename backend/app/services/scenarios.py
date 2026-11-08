"""场景 / 评分表 YAML 加载与校验（业务内容只在 YAML 中维护）。"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.core.errors import NotFound


class Objection(BaseModel):
    id: str
    text: str
    key: bool = False
    # 化解该异议时通常会涉及的要点，供评估提示词参考
    resolve_hints: list[str] = Field(default_factory=list)


class Persona(BaseModel):
    name: str
    role: str
    personality: str
    speaking_style: str
    background: str = ""
    budget: str | None = None
    hidden_needs: list[str] = Field(default_factory=list)
    objections: list[Objection] = Field(default_factory=list)


class StateRules(BaseModel):
    initial_trust: int = Field(30, ge=0, le=100)
    deal_threshold: int = Field(75, ge=0, le=100)
    hangup_threshold: int = Field(5, ge=0, le=100)
    # 最少对话轮数后才允许成交，避免"三句话被说服"
    min_turns_to_deal: int = 4
    max_gain_per_turn: int = 15
    max_loss_per_turn: int = 25


class Opening(BaseModel):
    speaker: Literal["user", "customer"] = "user"
    line: str | None = None
    # 给员工的开场提示（speaker=user 时显示）
    tip: str | None = None


class Scenario(BaseModel):
    id: str
    name: str
    department: list[str] = Field(default_factory=list)
    difficulty: int = Field(2, ge=1, le=5)
    max_turns: int = 15
    estimated_minutes: int = 5
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    background: str
    goal: str
    persona: Persona
    opening: Opening = Opening()
    state_rules: StateRules = StateRules()
    deal_line: str = "行，那你们安排一下，我们约个时间详细聊。"
    hangup_line: str = "算了，我还有事，先这样吧。"
    scoring: str
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self) -> "Scenario":
        r = self.state_rules
        if not r.hangup_threshold < r.initial_trust < r.deal_threshold:
            raise ValueError(f"场景 {self.id}: 需满足 hangup_threshold < initial_trust < deal_threshold")
        ids = [o.id for o in self.persona.objections]
        if len(ids) != len(set(ids)):
            raise ValueError(f"场景 {self.id}: 异议 id 重复")
        return self

    @property
    def key_objection_ids(self) -> set[str]:
        return {o.id for o in self.persona.objections if o.key}

    def objection(self, oid: str) -> Objection | None:
        return next((o for o in self.persona.objections if o.id == oid), None)


class Dimension(BaseModel):
    name: str
    weight: float = Field(gt=0)
    good: str = ""
    bad: str = ""


class Rubric(BaseModel):
    id: str
    name: str
    dimensions: list[Dimension]
    hint_penalty: float = 2
    hint_penalty_max: float = 10

    @property
    def total_weight(self) -> float:
        return sum(d.weight for d in self.dimensions)


class ScenarioRegistry:
    """启动时加载 scenarios/ 下的 YAML；rubrics/ 子目录为评分表。"""

    def __init__(self, scenarios: dict[str, Scenario], rubrics: dict[str, Rubric]):
        self.scenarios = scenarios
        self.rubrics = rubrics
        for s in scenarios.values():
            if s.scoring not in rubrics:
                raise ValueError(f"场景 {s.id} 引用了不存在的评分表 {s.scoring}")

    @classmethod
    def load(cls, root: Path) -> "ScenarioRegistry":
        rubrics = {}
        for f in sorted((root / "rubrics").glob("*.y*ml")):
            r = Rubric.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
            rubrics[r.id] = r
        scenarios = {}
        for f in sorted(root.glob("*.y*ml")):
            s = Scenario.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
            if s.id in scenarios:
                raise ValueError(f"场景 id 重复：{s.id}")
            scenarios[s.id] = s
        return cls(scenarios, rubrics)

    def list(self, department: str | None = None) -> list[Scenario]:
        items = [s for s in self.scenarios.values() if s.enabled]
        if department:
            items.sort(key=lambda s: department not in s.department)
        return items

    def get(self, scenario_id: str) -> Scenario:
        s = self.scenarios.get(scenario_id)
        if not s or not s.enabled:
            raise NotFound(f"场景不存在：{scenario_id}")
        return s

    def rubric_for(self, scenario: Scenario) -> Rubric:
        return self.rubrics[scenario.scoring]
