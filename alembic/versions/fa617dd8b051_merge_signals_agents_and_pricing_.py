"""merge signals agents and pricing migrations

Revision ID: fa617dd8b051
Revises: 319e6b366151, fa7cc00c5b22
Create Date: 2025-10-29 02:08:19.967506

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "fa617dd8b051"
down_revision: str | Sequence[str] | None = ("319e6b366151", "fa7cc00c5b22")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
