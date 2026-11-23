"""保存正式试卷发布快照。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_exam_publications"
down_revision = "0005_training_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_publications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("paper_id", sa.String(32), nullable=False),
        sa.Column("paper", JSONB(), nullable=False),
        sa.Column("sections", JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exam_publications_paper_id", "exam_publications", ["paper_id"])
    op.add_column("exam_attempts", sa.Column("publication_id", sa.BigInteger()))
    op.create_foreign_key(
        "fk_exam_attempt_publication", "exam_attempts", "exam_publications", ["publication_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_column("exam_attempts", "publication_id")
    op.drop_table("exam_publications")
