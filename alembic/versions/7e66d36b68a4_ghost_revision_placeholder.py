"""ghost_revision_placeholder

Revision ID: 7e66d36b68a4
Revises: 6e19576203a0
Create Date: 2025-09-21 18:45:00.000000

This is a placeholder migration for a ghost revision that appeared in production
but doesn't exist in the migration history. This allows Alembic to find the
revision and continue the migration chain properly.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7e66d36b68a4"
down_revision: str | Sequence[str] | None = "6e19576203a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - placeholder for ghost revision.

    This is a no-op migration that exists only to provide the missing
    revision 7e66d36b68a4 that somehow got set in production database
    but never existed in our migration files.
    """
    # No schema changes needed - this is just to fill the gap in the chain
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
