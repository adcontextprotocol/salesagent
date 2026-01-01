"""merge_all_heads

Revision ID: d0c0d908f805
Revises: 30acc1daf358, 58e9d3fdf1f6, add_oidc_logout_url
Create Date: 2026-01-01 13:48:51.798646

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d0c0d908f805"
down_revision: Union[str, Sequence[str], None] = ("30acc1daf358", "58e9d3fdf1f6", "add_oidc_logout_url")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
