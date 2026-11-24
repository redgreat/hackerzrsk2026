"""新增 AI 考试题库和答卷规则快照。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_exam_question_bank"
down_revision = "0006_exam_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_questions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scenario_id", sa.String(32), nullable=False),
        sa.Column("scenario_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stem_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("topic_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exam_questions_scenario_id", "exam_questions", ["scenario_id"])
    op.create_index("ix_exam_questions_status", "exam_questions", ["status"])
    op.add_column("exam_attempts", sa.Column("paper_snapshot", JSONB()))


def downgrade() -> None:
    op.drop_column("exam_attempts", "paper_snapshot")
    op.drop_table("exam_questions")
