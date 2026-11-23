"""智能清洗培训案例，与原始转写及人工修订分开。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_training_cleanup"
down_revision = "0004_event_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_cleanups",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_id", sa.BigInteger(), sa.ForeignKey("knowledge_events.id"), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("prepared_input", JSONB(), nullable=False, comment="已去标识的本次输入"),
        sa.Column("result", JSONB(), nullable=False, comment="培训改编，与原文分开"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("cost_yuan", sa.Numeric(12, 6), comment="未配置模型单价时为空"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="创建时间",
        ),
    )
    op.create_index("ix_training_cleanups_event_id", "training_cleanups", ["event_id"])


def downgrade() -> None:
    op.drop_table("training_cleanups")
