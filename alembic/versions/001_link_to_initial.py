"""Link to initial schema

Revision ID: 001
Revises: initial_schema
Create Date: 2025-08-01 12:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | Sequence[str] | None = "initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # This is just a linking migration, no actual changes
    pass


def downgrade() -> None:
    # This is just a linking migration, no actual changes
    pass
