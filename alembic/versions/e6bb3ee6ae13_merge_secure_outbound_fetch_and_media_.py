"""merge secure-outbound-fetch and media-buy-status heads

Revision ID: e6bb3ee6ae13
Revises: 6a52cf43ad75, 9b2d4f6c1a37
Create Date: 2026-08-28 23:35:56.806771

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e6bb3ee6ae13"
down_revision: str | Sequence[str] | None = ("6a52cf43ad75", "9b2d4f6c1a37")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
