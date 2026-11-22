"""Remove unused RAG document, preference, and request-log storage.

Revision ID: 0004_remove_rag_storage
Revises: 0003_chatbot_foundation
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_remove_rag_storage"
down_revision: Union[str, None] = "0003_chatbot_foundation"
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
