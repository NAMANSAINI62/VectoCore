"""Add policy_version column to cache_entries for guardrail policy isolation.

Revision ID: 0013_cache_entries_policy_version
Revises: a1b2c3d4e5fc
Create Date: 2026-11-22 13:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5fd"
down_revision = "a1b2c3d4e5fc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cache_entries",
        sa.Column(
            "policy_version",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pre-guardrails'"),
        ),
    )
    op.create_index("ix_cache_entries_policy_version", "cache_entries", ["policy_version"])


def downgrade() -> None:
    op.drop_index("ix_cache_entries_policy_version", table_name="cache_entries")
    op.drop_column("cache_entries", "policy_version")
