"""Add cache_telemetry blocked status check constraint and guardrail_events table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5fc"
down_revision = "a1b2c3d4e5fb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cache_telemetry
        DROP CONSTRAINT IF EXISTS ck_cache_telemetry_cache_status
        """
    )
    op.create_check_constraint(
        "ck_cache_telemetry_cache_status",
        "cache_telemetry",
        "cache_status IN ('exact_hit', 'semantic_hit', 'miss', 'bypass', 'error', 'blocked')",
    )

    op.create_table(
        "guardrail_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("user_id_hash", sa.String(length=64), nullable=False),
        sa.Column("layer", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("score_band", sa.String(length=32), nullable=False),
        sa.Column("detector", sa.String(length=80), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("message_hash", sa.String(length=64), nullable=False),
        sa.Column("message_length", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('shadow', 'enforce')",
            name="ck_guardrail_events_mode",
        ),
        sa.CheckConstraint(
            "decision IN ('ALLOW', 'BLOCK', 'REDACT', 'REQUIRE_REVIEW', 'FALLBACK')",
            name="ck_guardrail_events_decision",
        ),
        sa.CheckConstraint(
            "message_length >= 0",
            name="ck_guardrail_events_message_length",
        ),
    )
    op.create_index("ix_guardrail_events_request_id", "guardrail_events", ["request_id"])
    op.create_index("ix_guardrail_events_user_created", "guardrail_events", ["user_id_hash", "created_at"])
    op.create_index("ix_guardrail_events_layer_decision", "guardrail_events", ["layer", "decision"])


def downgrade() -> None:
    op.drop_index("ix_guardrail_events_layer_decision", table_name="guardrail_events")
    op.drop_index("ix_guardrail_events_user_created", table_name="guardrail_events")
    op.drop_index("ix_guardrail_events_request_id", table_name="guardrail_events")
    op.drop_table("guardrail_events")
    op.drop_constraint("ck_cache_telemetry_cache_status", "cache_telemetry", type_="check")
