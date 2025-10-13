"""merge property authorization and pricing options migrations

Revision ID: 00b3c68c3ac6
Revises: 0937c1edf84c, ad50e8fe9840
Create Date: 2025-10-13 00:05:50.961459

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "00b3c68c3ac6"
down_revision: str | Sequence[str] | None = ("0937c1edf84c", "ad50e8fe9840")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
