"""应用日志表（WARNING 及以上 + 4xx/5xx 请求，便于直接用 SQL 排查）

Revision ID: 0003_app_logs
Revises: 0002_collection_training
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_app_logs"
down_revision: str | None = "0002_collection_training"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("level", sa.String(16), nullable=False, comment="WARNING/ERROR/CRITICAL"),
        sa.Column("logger", sa.String(128), nullable=False, server_default="", comment="日志来源模块"),
        sa.Column(
            "message", sa.Text(), nullable=False, server_default="", comment="日志正文（不含对话内容）"
        ),
        sa.Column("exc", sa.Text(), comment="异常堆栈"),
        sa.Column("method", sa.String(8), comment="HTTP 方法（请求日志）"),
        sa.Column("path", sa.String(256), comment="请求路径（请求日志）"),
        sa.Column("status", sa.Integer(), comment="HTTP 状态码（请求日志）"),
        comment="应用日志：后端 WARNING 及以上、4xx/5xx 请求（不记录请求体与对话内容）",
    )
    op.create_index("ix_app_logs_created_at", "app_logs", ["created_at"])
    op.create_index("ix_app_logs_level_created", "app_logs", ["level", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_app_logs_level_created", table_name="app_logs")
    op.drop_index("ix_app_logs_created_at", table_name="app_logs")
    op.drop_table("app_logs")
