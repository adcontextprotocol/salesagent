"""merge inventory profiles and product details migrations

Revision ID: 039d59477ab4
Revises: 4efe7b2471a9, 149ad85edb6f
Create Date: 2025-11-08 19:44:50.788961

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "039d59477ab4"
down_revision: str | Sequence[str] | None = ("4efe7b2471a9", "149ad85edb6f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
