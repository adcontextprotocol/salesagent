"""Merge PR79 webhook fixes with creative_assignments from main

Revision ID: a7acdcb7b3d3
Revises: 6d6ac8d87c34, e17d03b0a79e
Create Date: 2025-10-04 09:41:34.397434

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a7acdcb7b3d3"
down_revision: str | Sequence[str] | None = ("6d6ac8d87c34", "e17d03b0a79e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
