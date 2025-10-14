"""merge dynamic format discovery with main

Revision ID: 2a2aaed3b50d
Revises: ab57bdcf4bd8, ef5672f3a134
Create Date: 2025-10-13 14:23:01.258764

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2a2aaed3b50d"
down_revision: str | Sequence[str] | None = ("ab57bdcf4bd8", "ef5672f3a134")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
