"""Extend existing conversation records for provider-aware chatbot streaming.

Revision ID: 0003_chatbot_foundation
Revises: 0002_rag_tables
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_chatbot_foundation"
down_revision: Union[str, None] = "0002_rag_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_conversations",
        sa.Column("selected_provider", sa.String(length=40), server_default="groq", nullable=False),
    )
    op.add_column("chat_messages", sa.Column("provider", sa.String(length=40), nullable=True))
    op.add_column("chat_messages", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column(
        "chat_messages",
        sa.Column("status", sa.String(length=20), server_default="completed", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "status")
    op.drop_column("chat_messages", "latency_ms")
    op.drop_column("chat_messages", "output_tokens")
    op.drop_column("chat_messages", "input_tokens")
    op.drop_column("chat_messages", "provider")
    op.drop_column("chat_conversations", "selected_provider")
