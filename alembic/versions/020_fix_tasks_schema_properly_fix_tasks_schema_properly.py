"""fix_tasks_schema_properly

Revision ID: 020_fix_tasks_schema_properly
Revises: 13a4e417ebb5
Create Date: 2025-08-31 16:58:53.407080

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "020_fix_tasks_schema_properly"
down_revision: Union[str, Sequence[str], None] = "13a4e417ebb5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
