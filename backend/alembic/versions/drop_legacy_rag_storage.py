"""Remove unused RAG document, preference, and request-log storage.

Revision ID: a1b2c3d4e5f4
Revises: a1b2c3d4e5f3
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f4"
down_revision: Union[str, None] = "a1b2c3d4e5f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_request_logs")
    op.execute("DROP TABLE IF EXISTS document_chunks")
    op.execute("DROP TABLE IF EXISTS knowledge_documents")
    op.execute("DROP TABLE IF EXISTS user_rag_preferences")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS citations")


def downgrade() -> None:
    raise NotImplementedError("RAG storage was removed permanently; restore from a backup if required.")
