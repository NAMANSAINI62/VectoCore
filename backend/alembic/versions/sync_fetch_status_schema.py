"""Sync telemetry fetch status constraint and drop removed-feature schema.

Revision ID: b2c3d4e5f6a2
Revises: b2c3d4e5f6a1
"""

from alembic import op

revision = "b2c3d4e5f6a2"
down_revision = "b2c3d4e5f6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Replace legacy 'bypass' status with 'fetch' for live MCP tool executions
    op.execute("ALTER TABLE cache_telemetry DROP CONSTRAINT IF EXISTS ck_cache_telemetry_cache_status")
    op.execute("UPDATE cache_telemetry SET cache_status = 'fetch' WHERE cache_status = 'bypass'")
    op.execute(
        """
        UPDATE cache_telemetry
        SET validation_explanation = REPLACE(
            validation_explanation,
            'bypassed global semantic cache for real-time freshness.',
            'fetched real-time web data.'
        )
        WHERE cache_status = 'fetch' AND validation_explanation LIKE '%bypassed global semantic cache%'
        """
    )
    op.execute(
        """
        ALTER TABLE cache_telemetry
        ADD CONSTRAINT ck_cache_telemetry_cache_status
        CHECK (cache_status IN ('exact_hit', 'semantic_hit', 'miss', 'fetch', 'error', 'blocked'))
        """
    )

    # 2. Drop obsolete tables and columns left behind by removed features
    op.execute("DROP TABLE IF EXISTS cache_response_variants CASCADE")
    op.execute("DROP TABLE IF EXISTS password_reset_tokens CASCADE")
    op.execute(
        """
        ALTER TABLE cache_telemetry
        DROP COLUMN IF EXISTS variant_reused,
        DROP COLUMN IF EXISTS translation_performed,
        DROP COLUMN IF EXISTS translation_failed,
        DROP COLUMN IF EXISTS translation_latency_ms,
        DROP COLUMN IF EXISTS embedding_latency_ms,
        DROP COLUMN IF EXISTS pgvector_search_latency_ms,
        DROP COLUMN IF EXISTS compatibility_latency_ms,
        DROP COLUMN IF EXISTS memory_context_tokens,
        DROP COLUMN IF EXISTS memory_summary_included,
        DROP COLUMN IF EXISTS memory_window_size,
        DROP COLUMN IF EXISTS related_candidates
        """
    )
    op.execute(
        """
        ALTER TABLE chat_conversations
        DROP COLUMN IF EXISTS summary,
        DROP COLUMN IF EXISTS summary_upto_message_id,
        DROP COLUMN IF EXISTS summary_updated_at,
        DROP COLUMN IF EXISTS summary_count
        """
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only cleanup migration; removed feature schema is not restored.")
