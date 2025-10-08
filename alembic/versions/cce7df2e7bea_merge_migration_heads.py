"""Merge migration heads

Revision ID: cce7df2e7bea
Revises: f408509cab1c, merge_heads_001
Create Date: 2025-10-08 15:05:16.429409

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "cce7df2e7bea"
down_revision: str | Sequence[str] | None = ("f408509cab1c", "merge_heads_001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
