"""业务表（LangGraph checkpoint / store 表由其官方 setup() 维护，不在此定义）。"""

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 1024


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "员工（只存工号与姓名部门，不存手机号等个人信息）"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    userid: Mapped[str] = mapped_column(String(64), unique=True, comment="企业微信 UserId / 工号")
    name: Mapped[str] = mapped_column(String(64), default="", comment="姓名")
    department: Mapped[str] = mapped_column(String(128), default="", comment="部门")
    source: Mapped[str] = mapped_column(String(16), default="wecom", comment="来源：wecom/dev")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(String(256), comment="H5 密码登录（scrypt）")
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", comment="pending/active/rejected/disabled"
    )
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user", comment="user/admin")
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, comment="审核人 users.id")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeSession(TimestampMixin, Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        Index("ix_practice_sessions_user_started", "user_id", "started_at"),
        {"comment": "陪练会话；id 同时作为 LangGraph thread_id"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(32), comment="场景 ID")
    scenario_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(
        String(16), default="ongoing", comment="ongoing/deal/hangup/max_turns/user_end"
    )
    mode: Mapped[str] = mapped_column(
        String(16), default="practice", server_default="practice", comment="practice/exam（考试禁用提示）"
    )
    exam_attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    turns: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    final_trust: Mapped[int | None] = mapped_column(Integer)
    total_score: Mapped[int | None] = mapped_column(Integer)
    report: Mapped[dict | None] = mapped_column(JSONB, comment="教练报告 JSON")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_yuan: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0), comment="模型+语音成本")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeMessage(TimestampMixin, Base):
    __tablename__ = "practice_messages"
    __table_args__ = (
        Index("ux_practice_messages_session_seq", "session_id", "seq", unique=True),
        {"comment": "对练逐条记录（含客户内心独白，练习结束前不对员工展示）"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practice_sessions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    turn: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(16), comment="user/customer/hint")
    content: Mapped[str] = mapped_column(Text)
    trust_delta: Mapped[int | None] = mapped_column(Integer)
    trust_after: Mapped[int | None] = mapped_column(Integer)
    inner_thought: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSONB)


class ModelUsage(TimestampMixin, Base):
    __tablename__ = "model_usage"
    __table_args__ = {"comment": "模型 / 语音调用计量（成本统计，不记录对话内容）"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    purpose: Mapped[str] = mapped_column(
        String(32), comment="customer/evaluator/coach/hint/embedding/asr/tts"
    )
    model: Mapped[str] = mapped_column(String(128), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    audio_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal(0))
    tts_chars: Mapped[int] = mapped_column(Integer, default=0)
    cost_yuan: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = {"comment": "话术知识库（RAG，内容必须已脱敏）"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(256), comment="来源文件")
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    scenario_ids: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, comment="空=通用")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class Recording(TimestampMixin, Base):
    __tablename__ = "recordings"
    __table_args__ = {"comment": "优质录音（音频留在 OSS，仅存地址；转写文本已脱敏）"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16), default="dbmcp", comment="dbmcp/file")
    source_key: Mapped[str] = mapped_column(String(128), unique=True, comment="来源唯一键，防重复导入")
    audio_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(128), default="")
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSONB, comment="来源附加信息（不含客户身份信息）")
    status: Mapped[str] = mapped_column(
        String(16), default="imported", comment="imported/transcribing/transcribed/analyzing/ready/failed"
    )
    error: Mapped[str | None] = mapped_column(Text)
    asr_task_id: Mapped[str | None] = mapped_column(String(128))
    transcript: Mapped[list | None] = mapped_column(JSONB, comment="[{begin_ms,end_ms,speaker,text}]")
    analysis: Mapped[dict | None] = mapped_column(JSONB, comment="AI 分析：亮点、合规、点评")
    customer_type: Mapped[str] = mapped_column(String(32), default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    published: Mapped[bool] = mapped_column(Boolean, default=False, comment="管理员审核后员工可见")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RecordingQuestion(TimestampMixin, Base):
    __tablename__ = "recording_questions"
    __table_args__ = {"comment": "听录音答题题目（AI 生成，管理员审核）"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16), default="single", comment="single/multi/judge")
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSONB)
    answer: Mapped[list] = mapped_column(JSONB, comment="正确选项下标")
    explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="pending/approved/rejected")


class ExamAttempt(TimestampMixin, Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        Index("ix_exam_attempts_user_paper", "user_id", "paper_id"),
        {"comment": "考试 / 自测作答记录"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    paper_id: Mapped[str] = mapped_column(String(32))
    paper_name: Mapped[str] = mapped_column(String(128), default="")
    kind: Mapped[str] = mapped_column(String(16), default="exam", comment="exam/self_test")
    status: Mapped[str] = mapped_column(String(16), default="in_progress", comment="in_progress/submitted")
    sections: Mapped[list] = mapped_column(JSONB, comment="出题快照（含答案，仅服务端使用）")
    answers: Mapped[dict] = mapped_column(JSONB, default=dict, comment="{题目key: [选项下标]}")
    result: Mapped[dict | None] = mapped_column(JSONB, comment="判分结果")
    score: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TranscriptSnapshot(TimestampMixin, Base):
    """同一来源的完整转写版本；原始导出只留私有文件，不存入此表。"""

    __tablename__ = "transcript_snapshots"
    __table_args__ = (UniqueConstraint("source_key", "source_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(128), index=True)
    source_hash: Mapped[str] = mapped_column(String(64))
    source_file: Mapped[str] = mapped_column(Text)
    source_labels: Mapped[str] = mapped_column(Text)
    segments: Mapped[list] = mapped_column(JSONB, comment="完整基础脱敏转写，保留编号、声道、原始时间")
    speaker_mapping: Mapped[dict] = mapped_column(JSONB)
    speaker_mapping_status: Mapped[str] = mapped_column(String(64))
    time_unit: Mapped[str] = mapped_column(String(32))
    privacy_status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")


class KnowledgeEvent(TimestampMixin, Base):
    """提取事件及向量；版本只追加，未审核事件不提供给检索。"""

    __tablename__ = "knowledge_events"
    __table_args__ = (UniqueConstraint("snapshot_id", "event_key", "extraction_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("transcript_snapshots.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(64))
    extraction_hash: Mapped[str] = mapped_column(String(64))
    extraction_version: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    segment_start: Mapped[int] = mapped_column(Integer)
    segment_end: Mapped[int] = mapped_column(Integer)
    evidence_seqs: Mapped[list] = mapped_column(JSONB)
    labels: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text)
    applicability_limits: Mapped[list] = mapped_column(JSONB)
    candidate_use: Mapped[str] = mapped_column(String(64))
    policy_verification: Mapped[str] = mapped_column(String(32))
    review_status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    review_data: Mapped[dict | None] = mapped_column(JSONB, comment="人工修订，与原始提取结果分开")
    review_history: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    review_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
