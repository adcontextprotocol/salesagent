"""merge_gam_line_item_creation_with_main

Revision ID: f408509cab1c
Revises: 018_platform_config, e2d9b45ea2bc
Create Date: 2025-10-07 10:04:55.848728

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f408509cab1c"
down_revision: str | Sequence[str] | None = ("018_platform_config", "e2d9b45ea2bc")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
