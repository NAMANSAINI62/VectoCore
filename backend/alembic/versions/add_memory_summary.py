"""Add short-term memory summary columns to chat_conversations and memory telemetry columns to cache_telemetry.

Revision ID: add_short_term_memory_summary
Revises: a1b2c3d4e5fd
Create Date: 2026-11-23 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_short_term_memory_summary"
down_revision = "a1b2c3d4e5fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "chat_conversations",
        sa.Column("summary_upto_message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "chat_conversations",
        sa.Column("summary_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "cache_telemetry",
        sa.Column("memory_context_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cache_telemetry",
        sa.Column("memory_summary_included", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "cache_telemetry",
        sa.Column("memory_window_size", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("cache_telemetry", "memory_window_size")
    op.drop_column("cache_telemetry", "memory_summary_included")
    op.drop_column("cache_telemetry", "memory_context_tokens")

    op.drop_column("chat_conversations", "summary_updated_at")
    op.drop_column("chat_conversations", "summary_upto_message_id")
    op.drop_column("chat_conversations", "summary")
