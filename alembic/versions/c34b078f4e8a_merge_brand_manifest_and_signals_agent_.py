"""merge brand manifest and signals agent migrations

Revision ID: c34b078f4e8a
Revises: 378299ad502f, fa617dd8b051
Create Date: 2025-10-29 11:05:34.957457

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c34b078f4e8a"
down_revision: str | Sequence[str] | None = ("378299ad502f", "fa617dd8b051")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
