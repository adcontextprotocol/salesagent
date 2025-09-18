"""fix_broken_migration_chain

Revision ID: 6e19576203a0
Revises: 4f80e016686e
Create Date: 2025-09-18 06:16:54.471135

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6e19576203a0"
down_revision: str | Sequence[str] | None = "4f80e016686e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - fixing broken migration chain.

    This migration handles the case where production database was
    migrated to revision f7e503a712cf which doesn't exist in the
    current migration chain. This is a no-op migration that just
    allows the chain to continue.
    """
    # No schema changes needed - this is just to fix the migration chain
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
