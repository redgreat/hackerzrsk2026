"""业务表（LangGraph checkpoint / store 表由其官方 setup() 维护，不在此定义）。"""

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
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
