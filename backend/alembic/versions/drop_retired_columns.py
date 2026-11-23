"""Historical migration slot retained for Alembic revision continuity."""

revision = "a1b2c3d4e5fa"
down_revision = "a1b2c3d4e5f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: the retired schema is intentionally not created."""


def downgrade() -> None:
    """No-op historical revision."""
