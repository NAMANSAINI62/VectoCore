"""Add cache_response_variants table and translation/variant telemetry columns.

Revision ID: a1b2c3d4e5f5
Revises: a1b2c3d4e5f4
Create Date: 2026-11-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f5"
down_revision: Union[str, None] = "a1b2c3d4e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cache_response_variants (
            id UUID PRIMARY KEY,
            cache_entry_id UUID NOT NULL REFERENCES cache_entries(id) ON DELETE CASCADE,
            language_code VARCHAR(20) NOT NULL,
            response_content TEXT NOT NULL,
            translation_source_language VARCHAR(20) NOT NULL DEFAULT 'en',
            translation_method VARCHAR(40) NOT NULL DEFAULT 'original',
            translation_version VARCHAR(20) NOT NULL DEFAULT 'v1',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_cache_response_variants_entry_lang UNIQUE (cache_entry_id, language_code)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cache_response_variants_entry_id ON cache_response_variants (cache_entry_id);"
    )
    op.execute("ALTER TABLE cache_telemetry ADD COLUMN IF NOT EXISTS requested_language VARCHAR(20) NOT NULL DEFAULT 'en';")
    op.execute("ALTER TABLE cache_telemetry ADD COLUMN IF NOT EXISTS variant_reused BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("ALTER TABLE cache_telemetry ADD COLUMN IF NOT EXISTS translation_performed BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("ALTER TABLE cache_telemetry ADD COLUMN IF NOT EXISTS translation_failed BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("ALTER TABLE cache_telemetry ADD COLUMN IF NOT EXISTS translation_latency_ms INTEGER NOT NULL DEFAULT 0;")


def downgrade() -> None:
    op.execute("ALTER TABLE cache_telemetry DROP COLUMN IF EXISTS translation_latency_ms;")
    op.execute("ALTER TABLE cache_telemetry DROP COLUMN IF EXISTS translation_failed;")
    op.execute("ALTER TABLE cache_telemetry DROP COLUMN IF EXISTS translation_performed;")
    op.execute("ALTER TABLE cache_telemetry DROP COLUMN IF EXISTS variant_reused;")
    op.execute("ALTER TABLE cache_telemetry DROP COLUMN IF EXISTS requested_language;")
    op.execute("DROP TABLE IF EXISTS cache_response_variants;")
