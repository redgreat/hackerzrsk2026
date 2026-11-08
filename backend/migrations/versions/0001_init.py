"""初始化业务表 + pgvector 扩展

Revision ID: 0001_init
Revises:
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("userid", sa.String(64), nullable=False, unique=True, comment="企业微信 UserId / 工号"),
        sa.Column("name", sa.String(64), nullable=False, server_default="", comment="姓名"),
        sa.Column("department", sa.String(128), nullable=False, server_default="", comment="部门"),
        sa.Column("source", sa.String(16), nullable=False, server_default="wecom", comment="来源：wecom/dev"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        comment="员工（只存工号与姓名部门，不存手机号等个人信息）",
    )

    op.create_table(
        "practice_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scenario_id", sa.String(32), nullable=False, comment="场景 ID"),
        sa.Column("scenario_name", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="ongoing",
            comment="ongoing/deal/hangup/max_turns/user_end",
        ),
        sa.Column("turns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hints_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_trust", sa.Integer()),
        sa.Column("total_score", sa.Integer()),
        sa.Column("report", postgresql.JSONB(), comment="教练报告 JSON"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cost_yuan", sa.Numeric(12, 6), nullable=False, server_default="0", comment="模型+语音成本"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        comment="陪练会话；id 同时作为 LangGraph thread_id",
    )
    op.create_index("ix_practice_sessions_user_id", "practice_sessions", ["user_id"])
    op.create_index("ix_practice_sessions_user_started", "practice_sessions", ["user_id", "started_at"])

    op.create_table(
        "practice_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practice_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(16), nullable=False, comment="user/customer/hint"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("trust_delta", sa.Integer()),
        sa.Column("trust_after", sa.Integer()),
        sa.Column("inner_thought", sa.Text()),
        sa.Column("meta", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        comment="对练逐条记录（含客户内心独白，练习结束前不对员工展示）",
    )
    op.create_index(
        "ux_practice_messages_session_seq", "practice_messages", ["session_id", "seq"], unique=True
    )

    op.create_table(
        "model_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column(
            "purpose",
            sa.String(32),
            nullable=False,
            comment="customer/evaluator/coach/hint/embedding/asr/tts",
        ),
        sa.Column("model", sa.String(128), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_seconds", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("tts_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_yuan", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        comment="模型 / 语音调用计量（成本统计，不记录对话内容）",
    )
    op.create_index("ix_model_usage_session_id", "model_usage", ["session_id"])
    op.create_index("ix_model_usage_user_id", "model_usage", ["user_id"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(256), nullable=False, comment="来源文件"),
        sa.Column("title", sa.String(256), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(64)), nullable=False, server_default="{}"),
        sa.Column(
            "scenario_ids",
            postgresql.ARRAY(sa.String(32)),
            nullable=False,
            server_default="{}",
            comment="空=通用",
        ),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("embedding", Vector(1024)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        comment="话术知识库（RAG，内容必须已脱敏）",
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_knowledge_chunks_scenarios ON knowledge_chunks USING gin (scenario_ids)")


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("model_usage")
    op.drop_table("practice_messages")
    op.drop_table("practice_sessions")
    op.drop_table("users")
