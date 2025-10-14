"""merge advertising_policy with format_id pricing migrations

Revision ID: 7a33a9be8c6c
Revises: 5aa137e89a99, 953f2ffedf29
Create Date: 2025-10-14 16:50:56.420504

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a33a9be8c6c'
down_revision: Union[str, Sequence[str], None] = ('5aa137e89a99', '953f2ffedf29')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
