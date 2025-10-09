"""merge_migration_heads

Revision ID: 1ce85bf58867
Revises: 62bc22421983, 8cce9697e412
Create Date: 2025-10-09 17:04:21.438740

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "1ce85bf58867"
down_revision: str | Sequence[str] | None = ("62bc22421983", "8cce9697e412")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
