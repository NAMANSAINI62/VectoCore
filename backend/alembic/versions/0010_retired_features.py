"""Historical migration slot retained for Alembic revision continuity."""

revision = "0010_guardrails_and_evaluations"
down_revision = "0009_nemotron_embed_2048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: the retired schema is intentionally not created."""


def downgrade() -> None:
    """No-op historical revision."""
