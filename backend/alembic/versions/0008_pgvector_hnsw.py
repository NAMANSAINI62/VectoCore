"""Enable pgvector extension, convert query_embedding to vector(384), and add HNSW cosine index.

Revision ID: 0008_pgvector_hnsw
Revises: 0007_semantic_match_insights
Create Date: 2026-11-16 19:42:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_pgvector_hnsw"
down_revision = "0007_semantic_match_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn = op.get_bind()
    udt = conn.execute(
        sa.text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'cache_entries' AND column_name = 'query_embedding'"
        )
    ).scalar()
    if udt != "vector":
        op.execute(
            "ALTER TABLE cache_entries "
            "ALTER COLUMN query_embedding TYPE vector(384) "
            "USING query_embedding::vector(384)"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cache_entries_embedding_hnsw "
        "ON cache_entries USING hnsw (query_embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cache_entries_embedding_hnsw")
    conn = op.get_bind()
    udt = conn.execute(
        sa.text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'cache_entries' AND column_name = 'query_embedding'"
        )
    ).scalar()
    if udt == "vector":
        op.execute(
            "ALTER TABLE cache_entries "
            "ALTER COLUMN query_embedding TYPE double precision[] "
            "USING query_embedding::double precision[]"
        )
