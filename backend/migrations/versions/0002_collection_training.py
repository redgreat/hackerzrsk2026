"""催收新人培训：账号密码与审核、对练考试模式、优质录音、考试作答

Revision ID: 0002_collection_training
Revises: 0001_init
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_collection_training"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(256), comment="H5 密码登录（scrypt）"))
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="active",
            comment="pending/active/rejected/disabled",
        ),
    )
    op.add_column(
        "users", sa.Column("role", sa.String(16), nullable=False, server_default="user", comment="user/admin")
    )
    op.add_column("users", sa.Column("reviewed_by", sa.BigInteger(), comment="审核人 users.id"))
    op.add_column("users", sa.Column("reviewed_at", TS))

    op.add_column(
        "practice_sessions",
        sa.Column(
            "mode",
            sa.String(16),
            nullable=False,
            server_default="practice",
            comment="practice/exam（考试禁用提示）",
        ),
    )
    op.add_column("practice_sessions", sa.Column("exam_attempt_id", postgresql.UUID(as_uuid=True)))
    op.create_index("ix_practice_sessions_exam_attempt_id", "practice_sessions", ["exam_attempt_id"])

    op.create_table(
        "recordings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="dbmcp", comment="dbmcp/file"),
        sa.Column(
            "source_key", sa.String(128), nullable=False, unique=True, comment="来源唯一键，防重复导入"
        ),
        sa.Column("audio_url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(128), nullable=False, server_default=""),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("meta", postgresql.JSONB(), comment="来源附加信息（不含客户身份信息）"),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="imported",
            comment="imported/transcribing/transcribed/analyzing/ready/failed",
        ),
        sa.Column("error", sa.Text()),
        sa.Column("asr_task_id", sa.String(128)),
        sa.Column("transcript", postgresql.JSONB(), comment="[{begin_ms,end_ms,speaker,text}]"),
        sa.Column("analysis", postgresql.JSONB(), comment="AI 分析：亮点、合规、点评"),
        sa.Column("customer_type", sa.String(32), nullable=False, server_default=""),
        sa.Column("tags", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
        sa.Column(
            "published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="管理员审核后员工可见",
        ),
        sa.Column("published_at", TS),
        sa.Column("play_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        comment="优质录音（音频留在 OSS，仅存地址；转写文本已脱敏）",
    )

    op.create_table(
        "recording_questions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "recording_id",
            sa.BigInteger(),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "type", sa.String(16), nullable=False, server_default="single", comment="single/multi/judge"
        ),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("answer", postgresql.JSONB(), nullable=False, comment="正确选项下标"),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
            comment="pending/approved/rejected",
        ),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        comment="听录音答题题目（AI 生成，管理员审核）",
    )
    op.create_index("ix_recording_questions_recording_id", "recording_questions", ["recording_id"])

    op.create_table(
        "exam_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("paper_id", sa.String(32), nullable=False),
        sa.Column("paper_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("kind", sa.String(16), nullable=False, server_default="exam", comment="exam/self_test"),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="in_progress",
            comment="in_progress/submitted",
        ),
        sa.Column("sections", postgresql.JSONB(), nullable=False, comment="出题快照（含答案，仅服务端使用）"),
        sa.Column(
            "answers",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
            comment="{题目key: [选项下标]}",
        ),
        sa.Column("result", postgresql.JSONB(), comment="判分结果"),
        sa.Column("score", sa.Integer()),
        sa.Column("passed", sa.Boolean()),
        sa.Column("started_at", TS, nullable=False, server_default=NOW),
        sa.Column("deadline_at", TS),
        sa.Column("submitted_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        comment="考试 / 自测作答记录",
    )
    op.create_index("ix_exam_attempts_user_id", "exam_attempts", ["user_id"])
    op.create_index("ix_exam_attempts_user_paper", "exam_attempts", ["user_id", "paper_id"])


def downgrade() -> None:
    op.drop_table("exam_attempts")
    op.drop_table("recording_questions")
    op.drop_table("recordings")
    op.drop_index("ix_practice_sessions_exam_attempt_id", "practice_sessions")
    op.drop_column("practice_sessions", "exam_attempt_id")
    op.drop_column("practice_sessions", "mode")
    for col in ("reviewed_at", "reviewed_by", "role", "status", "password_hash"):
        op.drop_column("users", col)
