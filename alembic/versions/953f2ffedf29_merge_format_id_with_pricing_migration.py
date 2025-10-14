"""merge_format_id_with_pricing_migration

Revision ID: 953f2ffedf29
Revises: f2addf453200, 39c5ac5558c7
Create Date: 2025-10-13 22:06:04.684481

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "953f2ffedf29"
down_revision: str | Sequence[str] | None = ("f2addf453200", "39c5ac5558c7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
