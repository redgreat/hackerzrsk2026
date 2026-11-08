"""模型结构化输出契约。"""

from pydantic import BaseModel, Field


class TurnEvaluation(BaseModel):
    trust_delta: int = Field(description="本轮信任值变化，范围 -25~20")
    resolved_objection_ids: list[str] = Field(default_factory=list, description="本轮被有效化解的顾虑 id")
    behaviors: list[str] = Field(default_factory=list, description="员工本轮关键行为标签")
    inner_thought: str = Field(description="客户第一人称内心独白，不超过 40 字")
    hangup: bool = Field(False, description="客户是否因员工严重失礼/违规而直接挂断")
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
