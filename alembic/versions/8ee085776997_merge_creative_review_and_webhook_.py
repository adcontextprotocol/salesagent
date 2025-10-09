"""merge creative review and webhook delivery heads

Revision ID: 8ee085776997
Revises: 37adecc653e9, cce7df2e7bea
Create Date: 2025-10-09 07:56:21.268717

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8ee085776997"
down_revision: str | Sequence[str] | None = ("37adecc653e9", "cce7df2e7bea")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
