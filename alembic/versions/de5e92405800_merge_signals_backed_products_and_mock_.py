"""Merge signals-backed products and mock approval migrations

Revision ID: de5e92405800
Revises: e38f2f6f395a, fa5cffb9582b
Create Date: 2025-10-25 08:53:38.895522

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "de5e92405800"
down_revision: str | Sequence[str] | None = ("e38f2f6f395a", "fa5cffb9582b")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
