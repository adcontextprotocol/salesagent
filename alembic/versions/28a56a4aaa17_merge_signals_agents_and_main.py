"""merge signals agents and main

Revision ID: 28a56a4aaa17
Revises: 024_add_signals_agents, e38f2f6f395a
Create Date: 2025-10-25 12:33:26.032746

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "28a56a4aaa17"
down_revision: str | Sequence[str] | None = ("024_add_signals_agents", "e38f2f6f395a")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
