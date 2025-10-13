"""merge property authorization and buyer ref migrations

Revision ID: ad50e8fe9840
Revises: 31ff6218695a, 5e48d3ddc7f2
Create Date: 2025-10-12 23:05:24.617272

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "ad50e8fe9840"
down_revision: str | Sequence[str] | None = ("31ff6218695a", "5e48d3ddc7f2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
