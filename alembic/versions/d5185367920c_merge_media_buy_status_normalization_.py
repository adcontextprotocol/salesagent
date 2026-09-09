"""merge media buy status normalization with signing heads

Revision ID: d5185367920c
Revises: 6371c0f43f54, 9b2d4f6c1a37
Create Date: 2026-09-02 17:26:24.809860

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d5185367920c"
down_revision: str | Sequence[str] | None = ("6371c0f43f54", "9b2d4f6c1a37")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
