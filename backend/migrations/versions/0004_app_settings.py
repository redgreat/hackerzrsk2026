"""运维配置覆盖表（非敏感项；密钥仍只放 config.yml）

Revision ID: 0004_app_settings
Revises: 0003_app_logs
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_app_settings"
down_revision: str | None = "0003_app_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by", sa.String(64)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="运维配置覆盖项（非敏感；密钥只放 config.yml）",
    )


def downgrade() -> None:
    op.drop_table("app_settings")
