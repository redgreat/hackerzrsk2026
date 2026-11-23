"""模型结构化输出契约。"""

from typing import Literal

from pydantic import BaseModel, Field, StrictBool


class TurnEvaluation(BaseModel):
    is_relevant: StrictBool = Field(description="本轮发言是否与当前练习相关")
    trust_delta: int = Field(description="本轮信任值变化，范围 -25~20")
    resolved_objection_ids: list[str] = Field(default_factory=list, description="本轮被有效化解的顾虑 id")
    behaviors: list[str] = Field(default_factory=list, description="员工本轮关键行为标签")
    inner_thought: str = Field(description="客户第一人称内心独白，不超过 40 字")
    hangup: bool = Field(False, description="客户是否因员工严重失礼/违规而直接挂断")
    red_line: str | None = Field(None, description="员工本轮触犯的合规红线（照抄红线原文），未触犯为 null")
    reason: str = Field("", description="评估理由，一句话")


class DimensionScore(BaseModel):
    name: str
    score: int = Field(ge=1, le=5)
    comment: str = ""


class TurnReview(BaseModel):
    turn: int
    user_said: str
    issue: str
    better_reply: str


class CoachOutput(BaseModel):
    summary: str
    dimension_scores: list[DimensionScore]
    highlights: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    turn_reviews: list[TurnReview] = Field(default_factory=list)
    red_line_violations: list[str] = Field(
        default_factory=list, description="触犯的合规红线，格式“第N轮：红线”"
    )


# ---------- 优质录音分析 ----------


class RecordingHighlight(BaseModel):
    index: int = Field(description="对应转写中 [序号] 的坐席句子")
    technique: str = Field(description="话术技巧名称，2~8 字，如“共情接话”“锁定承诺”")
    why: str = Field(description="为什么好，不超过 50 字")


class RecordingStage(BaseModel):
    name: str = Field(description="通话阶段，如 开场核实/了解原因/告知影响/协商方案/确认收尾")
    start_index: int


class RecordingQuestionDraft(BaseModel):
    type: Literal["single", "multi", "judge"] = "single"
    stem: str
    options: list[str] = Field(description='判断题固定为 ["正确", "错误"]')
    answer: list[int] = Field(description="正确选项下标（从 0 开始）")
    explanation: str = ""


class RecordingAnalysis(BaseModel):
    title: str = Field(description="录音标题，不超过 20 字，不含客户姓名")
    summary: str = Field(description="一句话概述通话经过与结果，不超过 60 字")
    customer_type: str
    outcome: str = Field(description="通话结果，如 承诺还款/部分还款/约定回电/拒绝还款/第三方转告")
    tags: list[str] = Field(default_factory=list, description="2~5 个话术标签")
    stages: list[RecordingStage] = Field(default_factory=list)
    highlights: list[RecordingHighlight] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    compliance_issues: list[str] = Field(default_factory=list, description="合规问题；没有则为空数组")
    learning_points: list[str] = Field(default_factory=list, description="给新人的 3~5 条学习要点")
    related_scenario_ids: list[str] = Field(default_factory=list)
    questions: list[RecordingQuestionDraft] = Field(default_factory=list)
