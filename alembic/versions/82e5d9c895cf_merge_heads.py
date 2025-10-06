"""merge heads

Revision ID: 82e5d9c895cf
Revises: 024_add_gam_sync_settings, a7acdcb7b3d3
Create Date: 2025-10-06 10:48:20.236971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82e5d9c895cf'
down_revision: Union[str, Sequence[str], None] = ('024_add_gam_sync_settings', 'a7acdcb7b3d3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
