"""Switch cache_entries embeddings to nvidia/nemotron-3.5-embed-1b (vector(2048)) and re-embed existing rows.

Revision ID: a1b2c3d4e5f9
Revises: a1b2c3d4e5f8
Create Date: 2026-11-18 00:46:30.000000
"""

from alembic import op
import sqlalchemy as sa

from app.services.embedding_service import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_MODEL_NAME,
    get_embedding_service,
)

revision = "a1b2c3d4e5f9"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("DROP INDEX IF EXISTS ix_cache_entries_embedding_hnsw")
    op.execute("ALTER TABLE cache_entries ALTER COLUMN query_embedding TYPE vector")

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, query FROM cache_entries "
            "WHERE embedding_dim != :dim OR embedding_model != :model "
            "ORDER BY created_at ASC"
        ),
        {"dim": DEFAULT_EMBEDDING_DIM, "model": DEFAULT_MODEL_NAME},
    ).fetchall()

    if rows:
        svc = get_embedding_service()
        batch_size = 16
        for start in range(0, len(rows), batch_size):
            chunk = rows[start : start + batch_size]
            queries = [str(r[1]) for r in chunk]
            vectors = svc.embed_batch(queries)
            for (row_id, _), vec in zip(chunk, vectors, strict=True):
                vec_str = "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"
                conn.execute(
                    sa.text(
                        "UPDATE cache_entries "
                        "SET query_embedding = CAST(:vec AS vector), "
                        "    embedding_dim = :dim, "
                        "    embedding_model = :model "
                        "WHERE id = :id"
                    ),
                    {
                        "vec": vec_str,
                        "dim": DEFAULT_EMBEDDING_DIM,
                        "model": DEFAULT_MODEL_NAME,
                        "id": row_id,
                    },
                )

    op.execute(f"ALTER TABLE cache_entries ALTER COLUMN query_embedding TYPE vector({DEFAULT_EMBEDDING_DIM})")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_cache_entries_embedding_hnsw "
        f"ON cache_entries USING hnsw ((query_embedding::halfvec({DEFAULT_EMBEDDING_DIM})) halfvec_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cache_entries_embedding_hnsw")
