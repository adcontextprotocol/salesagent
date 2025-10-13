"""merge creative_agents with pricing_options

Revision ID: ef5672f3a134
Revises: 0937c1edf84c, 33d3c9c61315
Create Date: 2025-10-13 00:43:42.623413

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "ef5672f3a134"
down_revision: str | Sequence[str] | None = ("0937c1edf84c", "33d3c9c61315")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
