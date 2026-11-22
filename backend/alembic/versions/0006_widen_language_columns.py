"""Widen language columns on cache_entries and cache_telemetry to String(80).

Revision ID: 0006_widen_language_columns
Revises: 0005_cache_response_variants
Create Date: 2026-11-15 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_widen_language_columns"
down_revision = "0005_cache_response_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "cache_entries",
        "detected_language",
        existing_type=sa.String(length=20),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
    op.alter_column(
        "cache_telemetry",
        "detected_language",
        existing_type=sa.String(length=20),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
    op.alter_column(
        "cache_telemetry",
        "requested_language",
        existing_type=sa.String(length=20),
        type_=sa.String(length=80),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "cache_telemetry",
        "requested_language",
        existing_type=sa.String(length=80),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "cache_telemetry",
        "detected_language",
        existing_type=sa.String(length=80),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "cache_entries",
        "detected_language",
        existing_type=sa.String(length=80),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
