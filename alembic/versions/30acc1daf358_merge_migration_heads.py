"""Merge migration heads

Revision ID: 30acc1daf358
Revises: a2a336ecb71d, add_auth_setup_mode
Create Date: 2025-12-31 00:07:20.405890

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "30acc1daf358"
down_revision: Union[str, Sequence[str], None] = ("a2a336ecb71d", "add_auth_setup_mode")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
