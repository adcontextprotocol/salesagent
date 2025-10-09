"""merge ai policy heads

Revision ID: bb73ab14a5d2
Revises: 4bec915209d1, merge_heads_001
Create Date: 2025-10-08 16:07:09.509385

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "bb73ab14a5d2"
down_revision: str | Sequence[str] | None = ("4bec915209d1", "merge_heads_001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
