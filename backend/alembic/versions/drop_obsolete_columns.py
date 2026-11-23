"""Remove obsolete monitoring and token-cost columns."""

from alembic import op


revision = "a1b2c3d4e5fb"
down_revision = "a1b2c3d4e5fa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluation_case_results")
    op.execute("DROP TABLE IF EXISTS evaluation_runs")
    op.execute("DROP TABLE IF EXISTS guardrail_events")
    op.execute(
        """
        ALTER TABLE cache_entries
        DROP COLUMN IF EXISTS guardrail_policy_version,
        DROP COLUMN IF EXISTS guardrail_approved,
        DROP COLUMN IF EXISTS guardrail_validated_at
        """
    )
    op.execute(
        """
        ALTER TABLE cache_telemetry
        DROP COLUMN IF EXISTS input_guardrail_latency_ms,
        DROP COLUMN IF EXISTS output_guardrail_latency_ms,
        DROP COLUMN IF EXISTS redis_lookup_latency_ms,
        DROP COLUMN IF EXISTS guardrail_decision,
        DROP COLUMN IF EXISTS guardrail_policy_version,
        DROP COLUMN IF EXISTS cost_saved_usd
        """
    )


def downgrade() -> None:
    raise RuntimeError("The removed schema is intentionally not restored.")
