"""merge migration heads

Revision ID: 6cc4765445a1
Revises: 5a0bd1eda2bd, 6ae57c13adca
Create Date: 2025-11-26 15:07:06.385361

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6cc4765445a1"
down_revision: Union[str, Sequence[str], None] = ("5a0bd1eda2bd", "6ae57c13adca")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
