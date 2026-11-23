"""知识事件人工修订与审核记录。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_event_review"
down_revision = "0003_transcript_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_events", sa.Column("review_data", JSONB(), comment="人工修订，与原始提取结果分开")
    )
    op.add_column(
        "knowledge_events", sa.Column("review_history", JSONB(), nullable=False, server_default="[]")
    )
    op.add_column(
        "knowledge_events", sa.Column("review_revision", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("knowledge_events", "review_revision")
    op.drop_column("knowledge_events", "review_history")
    op.drop_column("knowledge_events", "review_data")
