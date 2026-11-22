"""Add semantic match insights snapshot columns to cache_telemetry.

Revision ID: 0007_semantic_match_insights
Revises: 0006_widen_language_columns
Create Date: 2026-11-15 22:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_semantic_match_insights"
down_revision = "0006_widen_language_columns"
branch_labels = None
depends_on = None


_COLUMNS = [
    ("matched_entry_id", lambda: postgresql.UUID(as_uuid=True)),
    ("matched_query", sa.Text),
    ("response_preview", sa.Text),
    ("related_candidates", lambda: postgresql.JSONB(astext_type=sa.Text())),
    ("current_query", sa.Text),
    ("matched_queries_snapshot", lambda: postgresql.JSONB(astext_type=sa.Text())),
    ("rejected_candidates_snapshot", lambda: postgresql.JSONB(astext_type=sa.Text())),
    ("returned_response_snapshot", sa.Text),
    ("validation_explanation", sa.Text),
]


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _existing_columns("cache_telemetry")
    for col_name, type_factory in _COLUMNS:
        if col_name not in existing:
            op.add_column("cache_telemetry", sa.Column(col_name, type_factory(), nullable=True))


def downgrade() -> None:
    existing = _existing_columns("cache_telemetry")
    for col_name, _ in reversed(_COLUMNS):
        if col_name in existing:
            op.drop_column("cache_telemetry", col_name)
