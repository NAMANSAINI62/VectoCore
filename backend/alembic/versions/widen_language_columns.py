"""Widen language columns on cache_entries and cache_telemetry to String(80).

Revision ID: a1b2c3d4e5f6
Revises: a1b2c3d4e5f5
Create Date: 2026-11-15 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "a1b2c3d4e5f5"
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
