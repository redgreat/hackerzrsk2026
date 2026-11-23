"""新增完整转写版本与待审核知识事件。"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_transcript_events"
down_revision = "0002_collection_training"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_key", sa.String(128), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("source_labels", sa.Text(), nullable=False),
        sa.Column("segments", JSONB(), nullable=False, comment="完整基础脱敏转写，保留编号、声道、原始时间"),
        sa.Column("speaker_mapping", JSONB(), nullable=False),
        sa.Column("speaker_mapping_status", sa.String(64), nullable=False),
        sa.Column("time_unit", sa.String(32), nullable=False),
        sa.Column("privacy_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        sa.UniqueConstraint("source_key", "source_hash"),
    )
    op.create_index("ix_transcript_snapshots_source_key", "transcript_snapshots", ["source_key"])
    op.create_table(
        "knowledge_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_id", sa.BigInteger(), sa.ForeignKey("transcript_snapshots.id"), nullable=False),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("extraction_hash", sa.String(64), nullable=False),
        sa.Column("extraction_version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("segment_start", sa.Integer(), nullable=False),
        sa.Column("segment_end", sa.Integer(), nullable=False),
        sa.Column("evidence_seqs", JSONB(), nullable=False),
        sa.Column("labels", JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("applicability_limits", JSONB(), nullable=False),
        sa.Column("candidate_use", sa.String(64), nullable=False),
        sa.Column("policy_verification", sa.String(32), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("embedding", Vector(1024)),
        sa.Column("embedding_model", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        sa.UniqueConstraint("snapshot_id", "event_key", "extraction_hash"),
    )
    op.create_index("ix_knowledge_events_snapshot_id", "knowledge_events", ["snapshot_id"])


def downgrade() -> None:
    op.drop_table("knowledge_events")
    op.drop_table("transcript_snapshots")
