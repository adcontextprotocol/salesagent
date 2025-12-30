"""Merge migration heads

Revision ID: a2a336ecb71d
Revises: 46b1bf1c82c5, channel_to_channels
Create Date: 2025-12-30 05:20:04.956199

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2a336ecb71d"
down_revision: Union[str, Sequence[str], None] = ("46b1bf1c82c5", "channel_to_channels")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
