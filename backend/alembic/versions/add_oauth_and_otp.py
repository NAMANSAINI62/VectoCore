"""Add Google OAuth columns to users and create auth_otps table.

Revision ID: b2c3d4e5f6a1
Revises: add_short_term_memory_summary
Create Date: 2026-11-23 12:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, None] = "add_short_term_memory_summary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(32) NOT NULL DEFAULT 'local'")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_otps (
            id UUID PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            otp_hash VARCHAR(64) NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_otps_email ON auth_otps (email)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_auth_otps_email")
    op.execute("DROP TABLE IF EXISTS auth_otps")
    op.execute("DROP INDEX IF EXISTS ix_users_google_sub")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS google_sub")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auth_provider")
